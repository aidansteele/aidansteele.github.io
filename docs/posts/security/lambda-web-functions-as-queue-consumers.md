---
layout: post
title: Lambda Web Functions as queue consumers
date:
  created: 2026-10-12T23:55:00
categories:
  - AWS
---

[Lambda Web Functions][main-post] bill for the CPU you actually use, and queue
consumers spend most of their time waiting on something else. So is an SQS
consumer cheaper as a Web Function than as a regular Lambda function?

<!-- more -->

This is the last of three posts about [Lambda Web Functions][launch], which
AWS launched a few hours ago. I got too excited and wrote far more than I
normally would, so the [first post][main-post] covers the platform and the
[second][go-post] covers running Go on it via `execve()`. 

## Setup

The [launch post][launch] says Event Functions are "ideal for event
processing, queue consumers, and invocations triggered by other AWS services",
and Web Functions are for HTTP. That's a statement about the programming model,
not about billing. A queue consumer that spends 480ms of every 500ms waiting on
a downstream API is exactly the workload that concurrent requests per
environment and active-CPU billing would help.

Nothing stops you from (indirectly) pointing a queue at an HTTP
endpoint. [EventBridge Pipes](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-pipes.html)
will poll SQS, Kinesis, DynamoDB Streams or Kafka for you and deliver each
record to an [API destination](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-api-destinations.html),
which is just an HTTPS URL plus a connection that holds credentials. So I
tried it.

For these tests, the consumer is just a dummy: it does some CPU work for 15ms 
and then sleeps for 480ms. The CloudFormation looks something like:

```yaml
Connection:
  Type: AWS::Events::Connection
  Properties:
    AuthorizationType: API_KEY
    AuthParameters:
      ApiKeyAuthParameters:
        ApiKeyName: x-api-key
        ApiKeyValue: !Ref ApiKey

ApiDestination:
  Type: AWS::Events::ApiDestination
  Properties:
    ConnectionArn: !GetAtt Connection.Arn
    HttpMethod: POST
    InvocationEndpoint: !Sub "https://${ConsumerEndpoint.DomainName}/event"
    InvocationRateLimitPerSecond: 300

Pipe:
  Type: AWS::Pipes::Pipe
  Properties:
    RoleArn: !GetAtt PipeRole.Arn
    Source: !GetAtt Queue.Arn
    SourceParameters:
      SqsQueueParameters:
        BatchSize: 1
    Target: !GetAtt ApiDestination.Arn
    TargetParameters:
      InputTemplate: '{"messageId": <$.messageId>, "body": <$.body>}'
      HttpParameters:
        HeaderParameters:
          x-sqs-message-id: $.messageId
```

Some notes:

* [Connections only do API key, basic and OAuth](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-target-connection.html),
  not IAM, so the endpoint has to be `ApplicationManaged` and your app has to
  check the shared secret header itself. That's admittedly not great. 
* API destinations aren't a batchable target, so `BatchSize` must be 1 and every
  message is its own HTTP request. 
* If you write `InputTemplate: <$.body>` to pass the message through untouched, you get 
  a mangled body: `$.body` is a string, and EventBridge substitutes string values [with their JSON quoting
  removed](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-pipes-input-transformation.html#input-transform-implicit),
  so `{"n":42}` arrives as the unparseable `{n:42}`. Wrapping it in an object avoids that.

Then I put 2,000 messages each on queues being consumed by a Web Function and two
Event Functions: one at
128MB and one at 1,769MB (one full vCPU, so the CPU work runs at full speed). All
three drained. 

The event functions each spun up ~160 environments, hit 164
concurrent executions and kept pace with my `send-message-batch` loop,
finishing in 31 seconds. 

The Web Function was pinned to `maxEnvironments: 4`
by me, so it took 90 seconds, ran 4 environments at up to 14 concurrent
requests each, and shed 92 requests with `429 Platform.EndpointMaxEnvThrottle`
in the first 30 seconds while the per-environment limit bounced around. 
The Pipe retried some of those itself and sent 52 back to SQS, where they
sat out the queue's 60-second visibility timeout before being redelivered.
Nothing reached the DLQ. 

I don't know why the per-environment limit does that; it's the same thing I
saw [in the first post][main-post-concurrency]. Don't set `maxEnvironments`
as low as I did.

## Costs

The data comes from the platform's own metering: `REPORT` lines for the event functions, and
`platform.invokeSummary` CPU and memory for the Web Function, which meters
about 20ms of CPU per message (my code measures 15ms; the rest is HTTP and
logging) and about 200MB per environment. 

For the Web Function I've assumed an environment handling 14 concurrent 500ms 
requests (because this is what the platform settled on during my tests) so 
28 messages per second share that 200MB. Prices are us-east-1 arm64. I've 
ignored free tier and the cost of SQS, because that applies equally to both.

| per million messages | 128MB event function | 1,769MB event function | Web Function via Pipes |
|---|---|---|---|
| duration | 749ms (CPU-starved) | 505ms | ~500ms, 20ms of CPU |
| compute | $1.26 | $11.81 | $0.55 CPU + $0.03 memory |
| requests | $0.20 | $0.20 | $0.30 |
| Pipes + API destination | | | $0.40 + $0.20 |
| **total** | **$1.46** | **$12.01** | **$1.48** |

So against the smallest possible event function it's a dead heat, except that
the 128MB function takes 50% longer per message because it's getting 7% of a
vCPU. Against one with a full vCPU the Web Function is 8× cheaper. A more
realistic 512MB event function lands at about $3.80 per million (estimated). 
And the gap widens with I/O time: make the downstream call take
2 seconds instead of 480ms and the 128MB event function goes to about $4,
512MB to $14 and one vCPU to $48, while the Web Function goes to about $1.56,
because the extra time is just more requests sharing the same 200MB. $0.60 of
the Web Function's $1.48 is plumbing; the compute itself is $0.58.

Whether this is a good idea is a different question. You lose the 15-minute
timeout ([API destinations give up after 5 seconds](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-api-destinations.html)),
you lose batching, you lose partial-batch failure reporting, you're capped at
300 invocations per second per API destination unless you raise the quota, and
you have to rely on bearer tokens instead of Sigv4. But for a
high-volume consumer doing short, I/O-bound work, it's a lot cheaper. I suspect
AWS is never going to launch event-source mappings for Web Functions (because
then what would Event Functions be for?), so this will never be a _good_ fit, and
that feels like a shame to me.

[launch]: https://aws.amazon.com/blogs/aws/announcing-aws-lambda-web-functions-for-fast-consistent-web-app-performance-anywhere/
[main-post]: /blog/2026/10/12/some-notes-on-lambda-web-functions.html
[main-post-concurrency]: /blog/2026/10/12/some-notes-on-lambda-web-functions.html#behaviour
[go-post]: /blog/2026/10/12/go-on-lambda-web-functions-via-execve.html
