---
layout: post
title: Some notes on Lambda Web Functions
date:
  created: 2026-10-12T23:45:00
categories:
  - AWS
---

AWS launched Lambda Web Functions [a few hours ago][launch]. You give it a
Node.js app that listens on a port and Lambda runs it as-is behind an HTTPS URL,
with many concurrent requests per execution environment and billing for the CPU
time you actually use rather than wall-clock. There's no handler and no JSON
event. I deployed one, poked around inside it, and here are my notes. tl;dr: It
feels like taking the best of AWS Lambda, Google Cloud Run and Cloudflare Workers
and stuffing them together in a cohesive service.

<!-- more -->

I got a bit too excited about this one and wrote far more than I normally would,
so I've split it into three posts. This one is the platform: what's in the
execution environment, how it behaves, how it logs, and how it works behind
CloudFront, i.e. nerdy details that probably don't matter to many people.
The second is about [running Go on it via `execve()`][go-post],
because "Node.js only" turns out to be a soft limit. The third is about
[using a Web Function as an SQS consumer via EventBridge Pipes][queue-post]
and whether that's cheaper than an event function.

## History

I have a soft spot for this launch because I've been waiting for it since
December 2020. That's when I wrote [serverlessish][serverlessish], a small Go
program that let you run "any web server serverlessly in AWS Lambda" by sitting
between the Lambda runtime API and your real server running as a child process.
At pretty much the same time, [apparentorder][reweb-author] independently built
[re:Web][reweb], which did the same thing with more polish. In April 2021 Harold
Sun at AWS started what became the [Lambda Web Adapter][lwa], which has since
become the officially-blessed way to do this (and credits both projects in its
README, which is nice). But it was always a hack: one request at a time per
environment, billing by wall-clock duration while your app waited on IO (DynamoDB, S3, etc),
a 6MB payload limit because the request body had to be smuggled inside a JSON
event, and headers mangled by whichever event source you used.
[The docs](https://docs.aws.amazon.com/lambda/latest/dg/web-functions-runtimes.html)
now say, verbatim, "You don't need the AWS Lambda Web Adapter". Five and a bit
years from community hack to first-party feature is longer than I would have
liked, but better late than never!

## The shape of it

A Web Function is a container for two kinds of child resources:

**Revisions** are immutable snapshots of code + config (timeout, env vars, 
execution role, per-environment concurrency). Code comes from a *versioned* S3
bucket, and the bucket policy has to grant `lambda.amazonaws.com` access. You
can't upload a zip directly like you can with event functions.

**Endpoints** are HTTPS domains that route to one or two revisions by weight.
An endpoint is `HomeRegion`, `PerRegion` or `MultiRegion` - the last one gives
you a `<id>.lambda-web.global.on.aws` URL with latency-based routing. Auth is
either `ApplicationManaged` (i.e. none, bring your own) or `IamAuth` (SigV4,
or SigV4a for multi-region). CloudFront OAC supports the latter natively.

At launch it's `nodejs24.x` only (unless you use the approach mentioned in [my other post][go-post]),
arm64 only, 2 vCPU and 2GB only. There are only a few launch regions, but they
don't really matter - you can configure a function in us-east-1 and deploy
it to ap-southeast-2 (for example). You pay $0.30 per million requests, 
$0.0000276944 per vCPU-second of CPU your code actually burns, and $0.0000036667 
per GB-second of memory *consumed* (not configured) over the environment's lifetime. 
Those unit prices are identical to [Lambda MicroVMs][microvms-post], which made me
assume they share infrastructure. More on that below.

## Deploying with SAM

The launch post uses `aws lambda-web deploy`, which is a lovely one-shot command
that creates a bucket, a role, a function, a revision and an endpoint for you. It
even generates an `AGENTS.md` in the starter project, because it is 2026. But the
idea of not using infrastructure-as-code genuinely disturbs me, so I used SAM. 
There's a new `AWS::Serverless::WebFunction` resource that expands into
`AWS::Lambda::WebFunction`, `AWS::Lambda::WebFunctionRevision`,
`AWS::Lambda::WebFunctionEndpoint` and an IAM role:

```yaml
Transform: AWS::Serverless-2016-10-31

Parameters:
  CodeBucket: { Type: String }
  CodeKey: { Type: String }
  CodeVersion: { Type: String }

Resources:
  Probe:
    Type: AWS::Serverless::WebFunction
    Properties:
      Runtime: nodejs24.x
      AuthType: ApplicationManaged
      CodeUri:
        Bucket: !Ref CodeBucket
        Key: !Ref CodeKey
        Version: !Ref CodeVersion
      Timeout: 120
      MaxConcurrencyPerEnvironment: 4
      EnvironmentVariables:
        HELLO: world
      ScalingConfig:
        MaxEnvironments: 4

Outputs:
  Domain:
    Value: !GetAtt ProbeEndpoint.DomainName
```

A few things to note:

**The SAM CLI doesn't package Web Function code yet** (as of 1.168.0). `sam build`
and `sam deploy` won't zip a local `CodeUri` for you, so I had to wrap it in a shell script 
that zips, runs `aws s3api put-object` to capture the `VersionId`, and
passes it in as a parameter. Hopefully that's fixed soon.

**CloudFormation replaces the revision on every code change.** Revisions are
immutable, so an update creates a new revision, repoints the endpoint, and then
calls `DeleteWebFunctionRevision` on the old one (I watched it do so in
CloudTrail). That means the native `RevisionWeights` canary feature is awkward to
drive from CloudFormation: by the time the stack update finishes, the old
revision is gone. CodeDeploy-style traffic shifting for Web Functions would be
nice (like SAM supports for regular Lambda functions).

**Your local AWS CLI is probably too old.** Homebrew's `awscli` 2.37.12 has a
`lambda-web` subcommand with exactly one operation (`get-web-account-settings`) and
help text that says the commands are "experimental and for internal AWS use
only. They are not yet available to external customers". 2.37.13 has the full
set. I love a good pre-announcement leak.

**New accounts get smaller quotas than the docs say.** [The scaling docs](https://docs.aws.amazon.com/lambda/latest/dg/web-functions-scaling.html)
say 2,000 vCPUs and 100,000 RPS per region. `get-web-account-settings` on my account says 200
vCPUs (i.e. 100 environments) and 10,000 RPS.

## Inside the execution environment

I deployed a dependency-free `index.js` with routes that dump everything I could
think of, plus a token-protected `/exec` route for ad-hoc poking. Here's what I
found.

**The environment looks like a Lambda MicroVM.** PID 1 is
`/opt/amazon/asc/worker/bin/init --domain runtime --filesystem {"root":"/runtime",...}`,
the kernel is `6.18.48-109.150.amzn2023.aarch64.microvm`, the CPU is a Graviton4, 
and the root filesystem is a slimmed-down version of
the regular `nodejs:24` Lambda image - `/lambda-entrypoint.sh` is still sitting
in the root (unused?), and `dnf`, `rpm`, `curl`, `bash` and `openssl` are all
present. The VM had been up for 5 hours when my first request arrived, which
suggests VMs are pre-booted and sit in a pool before a customer's code is
attached. My Node process ran as `sbx_user1051` (uid 993) in a user namespace 
with no capabilities, so more similar to Lambda functions there.

**`/var/runtime/index.js` is the new runtime interface client**, and it's
surprisingly small (27KB of bundled TypeScript). It does the following:

1. `POST http://169.254.100.1:9001/2025-09-01/load` to the runtime API (body
   `{}`, no auth), which returns your env vars as a list of `KEY=value`
   strings plus a `runtimeConfiguration`. It `Object.assign`s the env vars
   into `process.env`, copies the log level into `AWS_LAMBDA_LOG_LEVEL`, and
   stashes the whole response on `globalThis.awsLambdaInternal.loadResponse`.
2. Monkey-patches `console.*` to emit JSON lines with `timestamp`, `level`,
   `requestId`, `endpointName` and `region`. Request ID comes from an
   `AsyncLocalStorage` that it populates by monkey-patching
   `http.Server.prototype.emit` to read the `lambda-web-request-id` header. So
   your logs are correlated to requests for free, as long as you use the
   built-in `http` module (more on logs later).
3. `import()`s your `/var/task/index.js` (or `AWS_LAMBDA_NODEJS_ENTRYPOINT`) with a
   9 second timeout.
4. Polls the port in `AWS_LAMBDA_HTTP_ENDPOINT` every 5ms until something
   accepts a TCP connection.
5. `POST /2025-09-01/ready`. Done. It never talks to the runtime API again.

There is also a hidden `--otel` flag that sets `OTEL_EXPORTER_OTLP_ENDPOINT` to
`http://otlp.localdomain:4318`. That hostname doesn't resolve today, so I assume
it's for something coming later.

**There is no extensions API.** `/2020-01-01/extension/register` and
`/2022-07-01/telemetry` both 404, as does the classic `/runtime/invocation/next`.
If your observability vendor's Lambda story is "install our extension", that story
doesn't apply here. You'll be shipping telemetry from inside your process, like
a normal web server. I think that's fine, but it's a change. Maybe it'll change later?

**The environment variables are sparse.** Here's the complete list:

| Name | Value |
|---|---|
| `AWS_EXECUTION_ENV` | `AWS_Lambda_nodejs24.x-lite` |
| `AWS_LAMBDA_INITIALIZATION_TYPE` | `native-http` |
| `AWS_LAMBDA_HTTP_ENDPOINT` | `0.0.0.0:3000` |
| `AWS_LAMBDA_RUNTIME_API` | `169.254.100.1:9001` |
| `AWS_LAMBDA_METADATA_API` | `169.254.100.1:9001` |
| `AWS_LAMBDA_METADATA_TOKEN` | a UUID |
| `AWS_LAMBDA_FUNCTION_MEMORY_SIZE` | `2048` |
| `AWS_LAMBDA_LOG_LEVEL` | `INFO` |
| `AWS_ACCOUNT_ID` | your account ID (new!) |
| `AWS_REGION`, `AWS_DEFAULT_REGION` | `us-east-1` |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` | role credentials |
| `NODE_PATH` | `/var/task` |
| `PWD` | `/var/task` |
| `SHLVL` | `0` |

Compare that to [the list for event functions][env-vars-post] I wrote down a
few years ago: no `PATH`, no `HOME`, no `LANG`, no `TZ`, no `_HANDLER`, no
`LAMBDA_TASK_ROOT`, no `AWS_LAMBDA_FUNCTION_NAME`, no
`AWS_LAMBDA_LOG_GROUP_NAME`. `AWS_ACCOUNT_ID` being there is a nice touch and
I'd like it in event functions too.

**But the function name and revision are in the process**, just not in the
environment. The `/load` response that the RIC stashes on
`globalThis.awsLambdaInternal.loadResponse` looks like this (env var values
elided):

```json
{
  "applicationConfiguration": ["EXEC_TOKEN=...", "HELLO=world"],
  "runtimeConfiguration": {
    "functionName": "Probe-ec9257c0",
    "functionVersion": "rev-vs8yl",
    "functionMemorySizeMB": 2048,
    "logConfig": {
      "level": "INFO",
      "groupName": "/aws/lambda/web/Probe-ec9257c0"
    }
  }
}
```

So the revision ID travels under the `functionVersion` name, and the log
group name is right there too. None of this comes from the sandbox: nothing
on the filesystem or in PID 1's command line mentions the function or
revision, and the only place it enters is that one HTTP response from
`169.254.100.1`, which is the host side of the MicroVM boundary. The RIC
doesn't expose any of it, so you have to read `globalThis.awsLambdaInternal`
and accept that it's named `Internal` for some reason. `POST /load` works strictly 
once per environment - calling it again from my app got an empty `500` - so you can't
just re-fetch it.

## Behaviour

**Lambda adds `x-forwarded-for`, `x-forwarded-proto`, `x-forwarded-port`,
`lambda-web-request-id` and `lambda-web-endpoint-name`** to inbound requests. It
strips client-supplied `lambda-web-*`, `X-Real-IP`, `Upgrade` and
`Connection`. It passes through `Forwarded`, `X-Amzn-Trace-Id` and `Cookie`
untouched. If you send two `Authorization` headers, one `AWS4-...` and one
`Bearer ...`, the SigV4-looking one is removed and the bearer one is delivered -
this is how CloudFront OAC and app-level auth coexist.

**Response headers are barely filtered.** My app set `lambda-web-custom`,
`x-forwarded-for: spoof`, `x-amzn-requestid: spoof`, `server: my-server` and
`via: 1.1 me` and every one of them reached the client. 

**Error types are in a response header.** Request timeout is
`504` with `Runtime.RequestTimeout` (at exactly `timeoutSeconds` + 1). A process
that exits mid-request is `503` with `Runtime.OriginRequestError`, and the next
request transparently gets a fresh environment. Throttling is `429` with 
`Platform.EndpointMaxEnvThrottle`. The HTML error bodies include the request ID.

**SSE streaming works** with no configuration. I got my first event ~1 second
after connecting and the rest at the cadence I sent them. Request bodies stream
too, with a [documented half-duplex caveat](https://docs.aws.amazon.com/lambda/latest/dg/web-functions-troubleshooting.html):
read the whole body before you write the response. **WebSockets don't.** 

**Cold starts are small.** `platform.initStart` to `platform.initReport` was 253ms
(130ms of CPU) for my dependency-free app, and a cold request took roughly half
a second longer than a warm one, so that's about the environment provisioning
overhead on top of init.

**The per-environment concurrency limit starts low and learns.** This was the
most surprising thing I found. `maxConcurrencyPerEnvironment` defaults to 64, but
that's a *ceiling* on a dynamic limit that Lambda manages. With `maxEnvironments:
4`, my first burst of 40 concurrent 3-second requests resulted in 4
environments, each handling 2-4 requests at once, and **30 of the 40 requests
being rejected with `429 Platform.EndpointMaxEnvThrottle`**. The next identical
burst had 10 rejected. The one after that had none, with ~10-14 per environment.
After a few more bursts it was comfortably doing 40 per environment. I may have
done something wrong here; scaling is normally the thing Lambda is good at.
**UPDATE**: If you leave the max environments unconfigured, there are no such
`429` errors. The platform instead overprovisions when it detects a burst of traffic.
I think this is how I will leave it in the future.

**You get one second after `SIGTERM`.** [The docs say so](https://docs.aws.amazon.com/lambda/latest/dg/web-functions-env-lifecycle.html) too. My
handler logged "still alive 500ms after SIGTERM" but not the 1500ms message, and
the platform logged `platform.spinDownReport` with `Runtime.SpinDownTimeout`
after 1059ms. Going by the `invokeReport` lifetimes, every environment I
created lived between 4.5 and 10.5 minutes; one that was started for a burst
but never received a request was reaped after 5m08s, so the idle timeout
looks like about five minutes. You're billed for memory over that whole
lifetime, so AWS is motivated to keep it short, and so are you.

## Logs

**The logs are good.** Every environment gets a stream named
`YYYY/MM/DD/<function>[<revision>]<instance>`, like regular functions. Lambda emits `platform.initStart`,
`platform.initReport`, `platform.invokeStart`, then one `platform.invokeSummary`
per minute with that minute's request count, peak concurrency, CPU
milliseconds and max memory, and finally `platform.invokeReport` and
`platform.spinDownStart`/`spinDownReport`. The `invokeReport` for one of my
environments said 78 requests, 810ms of CPU and 186MB over a 403 second
lifetime. By my arithmetic that's about $0.0003. **The `lambda-web-logstream`
response header tells you which stream served a given request, which is super
useful and I wish regular Lambda functions had it too.**

**There are two log groups, and which one you want depends on the endpoint
type.** Environments write to `/aws/lambda/web/<function>.local` in whichever
region they're running in, and Lambda asynchronously copies those events into
`/aws/lambda/web/<function>` in the home region, which [the logging docs](https://docs.aws.amazon.com/lambda/latest/dg/web-functions-logging.html#web-functions-logging-log-groups)
call the centralised group. That's true even for a `HomeRegion` endpoint: my
single-region functions all have both groups in us-east-1, and the `.local`
one is populated first. For the home region's own traffic the events reached
`.local` 3.5-9 seconds after they were logged and the centralised group 21-31
seconds after, with the `platform.invokeSummary` lines trailing the rest. It's
a bit weird that they're duplicated, but at least it's consistent.

To see the multi-region version I added a `MultiRegion` endpoint to the probe
function spanning us-east-1 and ap-southeast-2. It took about 90 seconds to go
`Active` in both regions. From Melbourne the global domain is a CNAME to
`<id>.735.lambda-web.ap-southeast-2.on.aws`, which is in turn a CNAME to
something under `ap-southeast-2.prod.frontend.lambda-lite.aws.dev` (the same
"lite" as in `AWS_EXECUTION_ENV`). The request ran in Sydney with
`AWS_REGION=ap-southeast-2`, a `/aws/lambda/web/<function>.local` group
appeared in ap-southeast-2 - and *only* `.local`; there's no centralised group
outside the home region - and 52 seconds later the same lines turned up in
us-east-1. In the centralised group the stream name grows a
`-<account>-<region>` suffix, so a Sydney environment's stream is
`2026/10/13/Probe-ec9257c0[rev-7ekjf]d358a4...-887559014507-ap-southeast-2`,
which is why [the docs](https://docs.aws.amazon.com/lambda/latest/dg/web-functions-logging.html#web-functions-logging-system-logs)
tell you to search the centralised group by stream name *prefix* when you've
got a `lambda-web-logstream` header in hand. I wonder whether it would have run
in Melbourne if I'd enabled the region. I was too lazy to find out today.

The cost consequence is that you're storing every log line at least twice.
Nothing is removed from `.local` after it's centralised, both groups are
created with never-expire retention, and the copy is free but the storage
isn't ([the monitoring docs](https://docs.aws.amazon.com/lambda/latest/dg/web-functions-monitoring.html)
are explicit about this). So a `MultiRegion` endpoint across N regions is
N+1 copies until you put a retention policy on each `.local` group in each
region plus the centralised one.

Earlier I mentioned that Lambda monkey-patches the logger. This is the
result:

```javascript
console.log("plain string log", req.url);
console.log({ msg: "object log", path: req.url, n: 42 });
console.warn("a warning with %s", "printf formatting");
console.error(new Error("an error object"));
console.debug("a debug line");
setTimeout(() => console.log("logged from a timer 50ms later"), 50);
```

CloudWatch gets this (one line each, pretty-printed here):

```json
{"timestamp":"2026-10-13T00:17:02.203Z","level":"INFO",
 "message":"plain string log /log?x=1",
 "requestId":"7FLJIHSO26GZ2DCJESP6MM62VE","endpointName":"prod","region":"us-east-1"}

{"timestamp":"2026-10-13T00:17:02.203Z","level":"INFO",
 "message":{"msg":"object log","path":"/log?x=1","n":42},
 "requestId":"7FLJIHSO26GZ2DCJESP6MM62VE","endpointName":"prod","region":"us-east-1"}

{"timestamp":"2026-10-13T00:17:02.204Z","level":"WARN",
 "message":"a warning with printf formatting",
 "requestId":"7FLJIHSO26GZ2DCJESP6MM62VE","endpointName":"prod","region":"us-east-1"}

{"timestamp":"2026-10-13T00:17:02.204Z","level":"ERROR",
 "message":{"errorType":"Error","errorMessage":"an error object",
            "stackTrace":["Error: an error object",
                          "    at Server.<anonymous> (/var/task/index.js:72:23)",
                          "    at Server.emit (node:events:514:28)",
                          "    at file:///var/runtime/index.js:641:35",
                          "    at AsyncLocalStorage.run (node:internal/async_local_storage/async_context_frame:65:14)",
                          "    at _InvokeStoreMulti.run (file:///var/runtime/index.js:582:21)",
                          "    at http.Server.emit (file:///var/runtime/index.js:636:28)",
                          "..."]},
 "requestId":"7FLJIHSO26GZ2DCJESP6MM62VE","endpointName":"prod","region":"us-east-1"}

{"timestamp":"2026-10-13T00:17:02.254Z","level":"INFO",
 "message":"logged from a timer 50ms later",
 "requestId":"7FLJIHSO26GZ2DCJESP6MM62VE","endpointName":"prod","region":"us-east-1"}
```

I like that they've injected the request ID and region. That will be super useful for
querying later in CWL Insights.

## CloudFront OAC does the whole HTTP

The docs' [recommendation](https://docs.aws.amazon.com/lambda/latest/dg/web-functions-endpoint-access-control.html#web-functions-endpoint-access-control-cloudfront) for custom domains
is an `IamAuth` endpoint behind CloudFront, with an origin access control of type `lambda` and
signing behaviour `always-amz-auth`. It's not GET-only like Lambda function
URLs.

There's no Web Function-specific policy resource, but the existing
[`AWS::Lambda::ResourcePolicy`](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-lambda-resourcepolicy.html)
accepts a web function ARN:

```yaml
HelloPolicy:
  Type: AWS::Lambda::ResourcePolicy
  Properties:
    ResourceArn: !Ref Hello  # the web-function/... ARN
    PolicyDocument:
      Version: "2012-10-17"
      Statement:
        - Effect: Allow
          Principal:
            Service: cloudfront.amazonaws.com
          Action: lambda:InvokeWebFunctionEndpoint
          Resource: !Ref HelloEndpoint
          Condition:
            StringEquals:
              aws:SourceArn: !Sub arn:aws:cloudfront::${AWS::AccountId}:distribution/${Distribution}
```

I sank too much time into a doc mistake: the syntax block on that docs page says the property is
`FunctionResourceArn`, but CloudFormation rejects that with
`Unsupported property [FunctionResourceArn]`. The example further down the
same page uses `ResourceArn`, and that's the one that works. (I've filed a doc bug report).

This works, and it works with 50MB request payloads (the biggest I tested). So it's a real
web server! But realistically, I think payloads that big are typically
something that could be sent directly to S3 anyway. 

## Feature requests for AWS

* `sam build`/`sam deploy` support for packaging Web Function code.
* A CodeDeploy-style traffic shifting integration, or at least a CloudFormation
  option to retain the previous revision.
* `AWS_LAMBDA_FUNCTION_NAME` and the revision ID as environment variables.
* More in the metadata endpoint: instance ID, revision, function ARN.
* An `--otel` that actually goes somewhere.
* Official support for other runtimes! I write Go - or at least my agents do. 
  The contract is already "listen on a port", so a `provided.al2023` equivalent
  is mostly a matter of AWS deciding to ship it.

## Overall

This is the Lambda I wanted in 2020. The programming model is "write a web
server" and the billing model stops punishing what our code spends most of its time doing
(waiting for someone else to respond). The rough edges are mostly typical AWS launching
an MVP (admittedly a very good one): Node-only, fixed 2 vCPU/2GB, no SAM CLI packaging, etc.
I can't wait to see how it evolves over time.

[launch]: https://aws.amazon.com/blogs/aws/announcing-aws-lambda-web-functions-for-fast-consistent-web-app-performance-anywhere/
[serverlessish]: https://github.com/glassechidna/serverlessish
[reweb]: https://github.com/apparentorder/reweb
[reweb-author]: https://github.com/apparentorder
[lwa]: https://github.com/awslabs/aws-lambda-web-adapter
[microvms-post]: /blog/2026/06/23/some-notes-on-lambda-microvms.html
[env-vars-post]: /blog/2022/12/15/lambda-extension-environment-variables.html
[go-post]: /blog/2026/10/12/go-on-lambda-web-functions-via-execve.html
[queue-post]: /blog/2026/10/12/lambda-web-functions-as-queue-consumers.html
