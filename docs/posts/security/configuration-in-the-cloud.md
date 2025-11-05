---
layout: post
title: Configuration in the cloud
date:
  created: 2022-10-19T23:14:52
categories:
  - AWS
---

<!-- more -->

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

## Less complaining, more demos

Check out [`cloudenv`][cloudenv]. It turns YAML ideas into usable demos:

![tada](/assets/2022-10-20-tada.png)

I just built it as a proof of concept to show that what I want is _technically_ 
possible and demonstrates a better (IMO) dev experience. I measure better as:

* Fewer Lambda-specific things to learn (and get wrong)
* Easy enough that people will use it

Keen to hear from folks about why I'm wrong, what might work better, etc.

[aws-blog]: https://aws.amazon.com/about-aws/whats-new/2022/10/aws-parameters-secrets-lambda-extension/
[ecs-blog]: https://aws.amazon.com/blogs/compute/securing-credentials-using-aws-secrets-manager-with-aws-fargate/
[12f]: https://12factor.net/config
[anc]: https://learn.microsoft.com/en-us/aspnet/core/fundamentals/configuration/?view=aspnetcore-6.0#non-prefixed-environment-variables
[cloudenv]: https://github.com/aidansteele/cloudenv
