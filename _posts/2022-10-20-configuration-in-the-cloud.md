---
layout: post
title: Configuration in the cloud
date: 2022-10-20 10:14:52 +1100
categories: blog
---

A couple of days ago, [_Announcing AWS Parameters and Secrets Lambda Extension_][aws-blog]
appeared on the AWS What's New site. The general thrust of the motivation behind 
this (providing an easier way to vend credentials securely to AWS Lambda functions)
is something that's absolutely needed, but I'm not sure that this approach will
move the needle - and it confuses me.

My confusion stems from how different an approach this is to how AWS ECS does it.
In June 2019, [AWS ECS released support][ecs-blog] for specifying secret values 
to be provided to ECS tasks at runtime. These secret values are fetched at 
container launch and provided to the process running inside the container as
regular environment variables. This is great because:

* [12 factor][12f] apps are encouraged to store configuration in environment variables
* Almost all application frameworks support it out of the box, integrating 
  environment values into their own configuration management systems, e.g.
  how [ASP.Net Core][anc] does it.
* Apps not using frameworks can access environment variables in a single line
  of code without requiring any dependencies.
* It mirrors how configuration can be injected by IDEs or Docker containers
  during local development.

I've been complaining about this for a while on Twitter:

![tweets](/assets/2022-10-20-tweets.png)

In my imagined _ideal state_ this configuration of secrets would become part
of the function configuration just like regular plain environment variables. So
the input to `UpdateFunctionCode` would look something like this:

![tweets](/assets/2022-10-20-ufc-json.png)

This would bring parity with AWS ECS to AWS Lambda and make porting apps between
the two a breeze, with no configuration code changes required. In an even more
perfect world, I would be able to define those secrets in AWS SAM (or CDK) and
have SAM automatically add the least-permissioned policies to the IAM policy for
the function, the same as it does for event sources, etc.

## Some assorted thoughts

**The approach taken in the Lambda layer allows for secrets to be reloaded at
runtime.** Is this a good thing? For one, it would be different to the behaviour
in AWS ECS, so will that receive the new dynamic reloading too? If anything, it
makes more sense in ECS than Lambda given that tasks in ECS will almost always
be longer-running than in Lambda. 

Plus I would personally argue that configuration changing at runtime isn't 
necessarily a good thing: by making it part of a versioned configuration 
(function configuration or ECS task definition) you have precise control over 
when the new values are used.

**The nature of the developer experience.** I've captured a screenshot of the
docs for this new Lambda layer. There's one layer, but there's two ([1][doc-1], [2][doc-2]) 
copies of the docs (one for each of the supported services) and they are 
mostly-but-not-actually the same.

![docs](/assets/2022-10-20-combined-docs.png)

Some issues with the docs:

* There's a different AWS account ID for each region. The Lambda Insights layer
  is all hosted in one layer, so you can have a `!Sub arn:aws:lambda:${AWS::Region}:580247275435:layer:LambdaInsightsExtension-Arm64:2`
  in your SAM template. This either requires committing to a region in your
  templates, or having a huge `Mappings` and `!FindInMap` in every template.
* Both docs say that the the extension can be configured by a number of environment
  variables, including `AWS_SESSION_TOKEN`. This one is a) apparently required but
  b) shouldn't be set by users. And why does it say it's used for validating request
  to prevent SSRF? It's an environment variable?
* This [tweet] clarifies that `AWS_SESSION_TOKEN` should be used as a request 
  header in customer code when calling `http://localhost:2773/...`. Now we 
  understand the comment in the docs, but it's not a required configuration env var.
* The advice to do `GET: /secretsmanager/get?secretId=secretId` is a bit weird
  on its own: what's the colon doing there? Where's the rest of the URL? We can
  deduce it from the default value specified for `PARAMETERS_SECRETS_EXTENSION_HTTP_PORT`.
* Is ARM support planned? Because this isn't an open source layer and there's no
  ETA we have to decide if it's worth switching back to x86_64 for this layer for
  some period of time. When ARM support does launch, we'll have to grow that sizeable
  `Mappings` I guess?
* The approach taken means that concurrency needs to be introduced into the customer
  code in order to fetch multiple parameters at once. If they're only fetching them
  once at launch, performance is better off using the `ssm:GetParameters` API directly.

I really don't mean to come across as unappreciative or too bitchy, but I think
that there's sufficient friction here that people just won't even _find_ this layer,
let alone use it. So they'll stick something in the Lambda function environment
variable and call it a day - and security suffers.

[aws-blog]: https://aws.amazon.com/about-aws/whats-new/2022/10/aws-parameters-secrets-lambda-extension/
[ecs-blog]: https://aws.amazon.com/blogs/compute/securing-credentials-using-aws-secrets-manager-with-aws-fargate/
[12f]: https://12factor.net/config
[anc]: https://learn.microsoft.com/en-us/aspnet/core/fundamentals/configuration/?view=aspnetcore-6.0#non-prefixed-environment-variables
[doc-1]: https://docs.aws.amazon.com/secretsmanager/latest/userguide/retrieving-secrets_lambda.html
[doc-2]: https://docs.aws.amazon.com/systems-manager/latest/userguide/ps-integration-lambda-extensions.html
[tweet]: https://twitter.com/OrenNachman/status/1582530677425131520
