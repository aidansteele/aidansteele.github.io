---
layout: post
title: "Graviton2: ARM comes to Lambda" 
date:
  created: 2021-09-29T03:37:52
categories:
  - AWS
---

<!-- more -->

Today, Amazon Web Services has unveiled [_AWS Lambda Functions Powered By AWS Graviton2 Processors_][release-link], 
offering a 20% reduction in the GB-second price compared to their x86-powered
cousins. But first, some short history.

## History

In 2015, AWS acquired Annapurna Labs. They were first tasked with building
the hardware that now powers the AWS Nitro system. But soon thereafter,
they turned their focus to compute and [launched the first generation of
Graviton-powered][graviton1] EC2 instances in the form of the `a1` instance family.

The next year, they launched [Graviton2][graviton2] with significant performance 
improvements over the first generation. This made them not only competitive with 
Intel and AMD's chips, but sometimes up to 40% better on a cost-performance basis
compared to current generation x86-based instances.

And that brings us to today. Graviton2, which has rolled out to Amazon EC2, Amazon RDS and
Amazon ElastiCache has made its way to AWS Lambda.

## tl;dr

It's almost always a no-brainer to switch to the new architecture. Here's how
you can do that for an example app written in Go:

```diff
--- a/cfn.yml
+++ b/cfn.yml
@@ -1,20 +1,20 @@
 Transform: AWS::Serverless-2016-10-31
 Resources:
   Function:
     Type: AWS::Serverless::Function
     Properties:
       Runtime: provided.al2
       Handler: my-app
       CodeUri: ./bootstrap
+      Architectures: [arm64]
       Policies:
         DynamoDBReadPolicy:
           TableName: example
       Events:
         Api:
           Type: HttpApi
diff --git a/build.sh b/build.sh
index 7f95be8..617824a 100755
--- a/build.sh
+++ b/build.sh
@@ -1,8 +1,8 @@
  #!/bin/sh
  
  export CGO_ENABLED=0
  export GOOS=linux
- export GOARCH=amd64
+ export GOARCH=arm64
 
  go build -o bootstrap
  sam deploy ...
```

Pretty easy, right? There's no need to install new tools, or mess around with
Docker, or rewrite your code. Just change (or set, if you didn't have it in the
first place) that `GOARCH` environment variable and you're good to go.

## Performance

Of course I was excited to see how the new architecture performed. Some folks had 
reported 28-65% performance gains for their workloads on EC2 instances! But that is extremely dependent on your workload.
In my case, my app is fairly [CRUDdy][crud]. There are parts that wait on the 
network, parts that read some JSON and write some slightly different JSON and
some business logic squeezed in between. So what performance gains did I see?

None. I made over 100,000 invocations of my functions in both `x86_64` and `arm64`
architecture options and it was impossible to tell them apart. Sometimes `arm64`
won, sometimes `x86_64` won. All in all, the difference was well within the margin
of noise.

So is it a disappointment? Hardly! I just saved 20% on my Lambda bill by changing
two lines of code. That's a great day in anyone's books. Or maybe I'll increase
the RAM allocated to my functions by 25% (= 1/.8) and have a faster execution 
time for the same price I was paying before. I guess I'll check the 
[Lambda Power Tuning][tuning] tool to see if that's worthwhile.

## Still need convincing?

Maybe your business depends on your Lambda functions being rock solid and you don't
want to risk trying something new. That's fair enough. Lambda supports 
[alias routing configurations][alias-routing]: a feature where you can send x%
of a function's traffic to one version of the function and the remaining 100-x%
to a _different_ version of the same function. So you can have two different
[versions][versioning] of the same function - one with `x86_64` and one with 
`arm64` - and incrementally shift traffic as slowly as it takes to build your
confidence. 

tl;dr: AWS have made it very easy to try out the new architecture. You might
as well give it a shot. They've measured up to **34%** price-performance
improvement over x86-based Lambda functions. 

[release-link]: https://aws.amazon.com/blogs/aws/aws-lambda-functions-powered-by-aws-graviton2-processor-run-your-functions-on-arm-and-get-up-to-34-better-price-performance/
[graviton1]: https://aws.amazon.com/blogs/aws/new-ec2-instances-a1-powered-by-arm-based-aws-graviton-processors/
[graviton2]: https://aws.amazon.com/blogs/aws/new-m6g-ec2-instances-powered-by-arm-based-aws-graviton2/
[crud]: https://en.wikipedia.org/wiki/Create,_read,_update_and_delete
[tuning]: https://docs.aws.amazon.com/lambda/latest/operatorguide/profile-functions.html
[alias-routing]: https://docs.aws.amazon.com/lambda/latest/dg/configuration-aliases.html#configuring-alias-routing
[versioning]: https://docs.aws.amazon.com/lambda/latest/dg/configuration-versions.html
