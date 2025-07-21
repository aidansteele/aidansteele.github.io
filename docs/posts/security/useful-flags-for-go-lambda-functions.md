---
layout: post
title: Useful flags for Go Lambda functions
date:
  created: 2023-08-02T04:04:00
categories:
  - AWS
---

<!-- more -->

Last week AWS published a [blog post][aws-blog] advising that the `go1.x` Lambda
runtime will be deprecated and people should migrate to `provided.al2`. I was 
already using the newer runtime, but I also learned from the blog post that AWS
SAM can now build Go Lambda functions for the newer runtime - no more Makefiles
required!

I switched from `BuildMethod: makefile` to `BuildMethod: go1.x` and noticed that
my Lambda packages were now twice the size. This means slower cold starts and 
slower deployments - especially from my laptop in Australia. I also noticed that 
my CI pipelines were slower because every commit was causing Lambda updates, even
when no code had changed. 

The cause of all these issues was the set of build-time flags. My Makefile was
setting them, but the AWS SAM builder [defaults][builder-flags] to no flags. The
problem can be addressed by setting the following environment variable 
_while building_ (i.e. in your CI system):

    export GOFLAGS="-buildvcs=false -trimpath '-ldflags=-s -w -buildid='"

Setting this environment variable halved the size of my Lambda packages and
caused update churn to go away, meaning faster CI. Breaking down the flags:

Three of the flags relate to deterministic builds. `-buildvcs=false` causes Go 
to not embed the Git commit hash and date in the built binaries. This can be 
useful for distributed tools, but causes every commit to generate unique Lambda 
package ZIPs - not what I wanted. The linker flag `-buildid=` is the same: it 
tells Go not to embed a unique hash in the binary. `-trimpath` is similar: it 
tells Go not to embed the absolute paths of packages in the binary. This means 
deploying from my laptop (where the code lives under `/Users/aidan/dev/...`) 
and from CI (where it could be anything!) will produce the same binaries.

The other two flags relate to binary size. The `-s` linker flag causes the Go
linker to omit the symbol table from the binary. Note that this does **not**
affect stacktraces. If your function panics, you still get a full stack trace
with function names and line numbers. The `-w` linker flag causes the Go linker
to omit DWARF data from the binary. This means the binary can't (usefully) be
controlled by a debugger, but that's not relevant in the Lambda environment.

[aws-blog]: https://aws.amazon.com/blogs/compute/migrating-aws-lambda-functions-from-the-go1-x-runtime-to-the-custom-runtime-on-amazon-linux-2/
[builder-flags]: https://github.com/aws/aws-lambda-builders/blob/e575e40f6ffdc8db4d450e5b863b035ac679550b/aws_lambda_builders/workflows/go_modules/builder.py#L67
