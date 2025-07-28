---
layout: post
title: Federating into Azure, GCP and AWS with OIDC
date:
  created: 2025-07-27T06:34:52
categories:
  - Azure
  - GCP
  - AWS
  - OIDC
---

<!-- more -->

Recently, I've been learning more about GCP and Azure. Specifically, I wanted 
to know the best way to federate into another organisation's projects/subscriptions
and whether there was any common ground with AWS, e.g. OIDC. What I learned is 
that the state of the art seems to be... a bit lacklustre? Long-term credentials
abound, even at the vendors that I consider to be best-in-class (Datadog, etc.)

This isn't really the clouds' fault per se, as I see that both GCP and Azure support
federation using OIDC. Maybe the functionality was introduced too recently, and
inertia is holding back vendors? In any case, I figured I should try do it myself
and see if maybe there was some show-stopping reason so few vendors are doing it.

And that's how we ended up with today's blog post: a real world example of federating
into Azure, GCP and AWS using OIDC. I wrote this because I genuinely couldn't find 
code-level examples for the first two clouds elsewhere.
I found plenty of blogs and docs about how to use OIDC to enable secretless 
federation between GitHub, Azure DevOps, etc - but none on how a vendor should
do it themselves! Could that be why it doesn't exist yet: because it hasn't been
explained?

## The first step: deploy everything

I've created a GitHub repo named [`cloudfed`][cloudfed]. It is a Terraform project
that consists of four modules:

`idp`: This module implements the publicly-accessible part of an OIDC identity
provider. Specifically, it provisions a KMS key (hosted in AWS KMS), a Lambda 
function and a URL for that function. The function serves two paths: `/.well-known/openid-configuration`
and `/.well-known/jwks`. The first one is defined in the OIDC spec. The second
one is referenced by the first one and contains the RSA public key in JWKS format
as per the spec.

`azure`, `gcp` and `aws`: These modules implement the resources required to 
federate into their corresponding clouds using an OIDC token. More on these in each
of the following sections.

In order to deploy these resources, you will need an Azure tenant, a GCP organization
and an AWS account. The free tier is fine for all of these. Clone the repo, edit the
values in `main.tf` and run `terraform apply`.

## The second step

`terraform apply` should yield a handful of outputs. These will need to be inserted
into `azure/azure.go`, `gcp/gcp.go`, `aws/aws.go` and `oidc/generate_oidc.go`. There
are placeholder constants in each file.

Once that's done, you're ready to go! Simply `cd` into each directory and `go run azure.go` 
(etc) to your heart's content. The code isn't perfect, but it should be a reasonable
starting point (e.g. it handles refreshing credentials when they expire, etc.)

Each Go package does the moral equivalent of enumerating storage buckets in an 
account/project/subscription, so if you want to see some output you'll need
to create some (free) buckets. Empty buckets are fine.

## Azure specifics

I'm still wrapping my head around Azure. There appear to be a couple of different
ways to do OIDC federation. One is directly configured on a "user-assigned managed
identity", which seems like the equivalent of an IAM role? The other is to create
an application in Entra ID (which itself seems more of a sibling to Azure than an
Azure service itself), configure OIDC on that application, and then assign that
application roles in Azure subscriptions. 

It's worth noting (especially if you're mostly an AWS person, like me) that these
"roles" are like permissions in AWS, and they can be assigned at relatively 
arbitrary scopes. You can assign them at the subscription level (mostly equivalent
to AWS accounts), or you can assign them at a "management group" level, which seem
equivalent-ish to AWS organization units. Technically, you can also assign them at
lower resource-based levels, too.

NOTE: The role assignment resource is `azurerm_role_assignment` and the `azurerm`
provider needs to be configured with a subscription, but if you specify a management
group scope, does the resource really belong to a subscription? Stay tuned while I
figure that out (or get in touch and explain it to me, please)

## GCP specifics

GCP is more similar to AWS than Azure in that the resource type (`google_iam_workload_identity_pool_provider`)
that creates an OIDC IdP belongs to a project, but it's more similar to Azure 
than AWS in that IAM permissions can be assigned to principals in the workload 
identity pool at the organisation level. My example Terraform module does exactly
this: grants the `viewer` role across the whole organization. Is that a bad idea?
I guess I'll find out soon if a reader contacts me and lets me know!

[cloudfed]: https://github.com/aidansteele/cloudfed