---
layout: post
title: Some notes on Lambda MicroVMs
date:
  created: 2026-06-23T04:43:00
categories:
  - AWS
---

AWS launched Lambda MicroVMs [earlier today][launch]. They're quite cool, and I
imagine they'll become quite popular quite quickly. Here are some notes on 
things I've discovered about them today.

<!-- more -->

Lambda MicroVMs are well-explained by the above blog post, but I'll quickly explain
here too for the lazy. MicroVMs are almost a generalisation of Lambda functions,
or a specialisation of EC2 instances. They're similar to containers, but more 
isolated, and more powerful (MicroVMs can run containers). You provide some code,
Lambda will run it in a new VM, within seconds, for up to 8 hours. Use cases include
CI runners, coding agent hosts, game servers, specialist web servers, etc. 

**You can get a shell in a MicroVM**. When I saw they launched, my first thought was
"do they have `/dev/ptmx`?" (because Lambda functions don't) - and they do. Not
only do they allow ptys, it's a first class citizen: you can call the
`CreateMicrovmShellAuthToken` API and connect straight to them, no reverse-shell
tomfoolery required.

**You can enable all operating system capabilities in a MicroVM**. Want to run
Docker containers inside a MicroVM? You can do that. Docker absolutely works. I
had a version mismatch with containerd out of the box, but it was solvable using
`dockerd --containerd=/run/containerd/containerd.sock`

**All outbound UDP is blocked by default**. The default DNS resolver is a localhost
stub. This causes DNS in a container to fall back to 8.8.8.8, which fails. The
solution is to run a container with Lambda DNS: `docker run --dns 169.254.169.253`.
UDP works fine through a VPC, explained next.

Alternatively, you can create a "Lambda network connector". Think of these as
reified VPC configurations. First you create a network connector with a few
configuration options:

* Subnet IDs
* Security group IDs
* IPv4/Dual-stack
* An IAM role capable of managing ENIs

Then you have your network connector, complete with its own lifecycle (i.e. wait
until it's `ACTIVE`) and ARN. You use that ARN when creating the MicroVM image
and/or when launching MicroVMs. This provides a nice separation of concerns.
A network team can create network connectors, and allow developers to only
use pre-existing connectors. 

!!! note "No more shenanigans"
    A note for cheapskates: back in 2021 I learned that you can attach an elastic
    IP address to the Lambda ENI and get internet connectivity from your 
    VPC-attached Lambda functions on the cheap. I even made a little [tool][lambdaeip]
    to automate that. You can no longer do that: AWS have put a resource-based
    policy on the ENIs that only allows mutations by the Lambda service. I guess
    they got sick of my shit.

**MicroVM images are built by Lambda, not you**. The UX felt weird at first: why do
I provide a Dockerfile inside a ZIP file and store it in S3? Why not let me 
just upload a Docker image? It becomes clear once you create your first image:
Lambda actually creates two copies of the image, one for Graviton 3 and one for
Graviton 4. By asking us to upload the "source" Dockerfile and code, they can
recompile on-demand.

**MicroVMs have the equivalent of "Lambda SnapStart"**. Specifically, AWS launches
the image during the build process and takes a snapshot of memory/disk. This
snapshot is then used to launch new MicroVMs. You'll probably want to take
advantage of the lifecycle hooks to reinitialise sources of randomness upon
MicroVM creation. 

**Inbound connectivity to MicroVMs is always authenticated**, using bearer tokens.
Connectivity is supported using HTTP/1.1, HTTP/2, gRPC, websockets and server-sent
events. You need to provide an `X-aws-proxy-auth` header. The value for that 
comes from calling `CreateMicrovmAuthToken`. Ingress can also be disabled 
altogether, if you want that. 

**Performance**: creating a MicroVM image takes 2-3 minutes. In my tests, going from
`RunMicrovm` to `RUNNING` state takes about 2 seconds, and apps actually serving
`HTTP 200 OK` takes a further 2 seconds. Suspending takes about a second. 
Resumption takes a second too, and apps serving `HTTP 200 OK` takes a further
second after that. Take those numbers with a grain of salt, because I'm connecting
to us-east-1 from the other side of the world.

**Tags**: the docs say to create IAM roles with trust policies that allow `sts:TagSession`.
As best I can tell, no session tags are passed right now. I confirmed this by
even creating roles without that permission in the trust policy and it
still worked. Presumably AWS just wanted to future-proof things, but it would
be good to know what tags they have in mind - or at least a tag name prefix so
we can scope it down slightly.

The token returned by `sts:GetWebIdentityToken` includes no claims about the
identity of the MicroVM. Hopefully that's coming soon. Lambda _functions_ include
a `lambda_source_function_arn` claim, so hopefully MicroVMs get something 
equivalent too. Even just a session tag would be sufficient.

All in all, I think this new functionality will be a supremely powerful building 
block. I've long wanted a way to be able to "address" individual Lambda execution
environments. AWS has provided exactly that, and their initial launch has a lot
of polish. The hardest part will be unlearning some of the architectural lessons
I've internalised over the years and making the best possible use of what we can
now do. 

[launch]: https://aws.amazon.com/blogs/aws/run-isolated-sandboxes-with-full-lifecycle-control-aws-lambda-introduces-microvms/
[lambdaeip]: https://github.com/glassechidna/lambdaeip
