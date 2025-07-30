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

Lately, I've been interested in how third party vendors can best authenticate
into their customers' cloud accounts. The status quo in AWS is usually role assumption
from the vendor's account to the customers', but what about GCP and Azure? Can
OIDC be used to authenticate into all three clouds in approximately the same way?
I think the answer is yes, and this blog post aims to show how to do so.

<!-- more -->

I've been learning more about GCP and Azure recently. Specifically, whether it is 
possible to de-duplicate federation logic between the clouds using OIDC. My partner 
was a big help here. They did a lot of research and experimentation and got all the
code working. I terraformed the setup and wrote this blog post. 

I wanted to write this because I genuinely couldn't find code-level examples for 
GCP or Azure elsewhere. I found plenty of blogs and docs about how to _use_ OIDC 
to enable secretless federation between GitHub, Azure DevOps, etc - but none on 
how a vendor should do it themselves! So this blog post aims to serve as an example
of how I'd love to see vendors federate into my cloud accounts.

## The first step: deploy everything

I've created a GitHub repo named [`cloudfed`][cloudfed]. It is a Terraform project
that consists of four modules:

`idp`: This module implements the publicly-accessible part of an OIDC identity
provider. Specifically, it provisions a KMS key (hosted in AWS KMS), a Lambda 
function and a URL for that function. The function serves two paths: `/{tenant}/.well-known/openid-configuration`
and `{tenant}/.well-known/jwks` as per the OIDC spec.

`azure`, `gcp` and `aws`: These modules implement the resources required to 
federate into their corresponding clouds using an OIDC token. More on these in each
of the following sections.

In order to deploy these resources, you will need an Azure tenant, a GCP organization
and an AWS account. The free tier is fine for all of these. Clone the repo, edit the
values in `vars.auto.tfvars` and run `make deploy`.

## The second step

You can now run `make run`. That will in turn run each of the sample apps to federate
into AWS, GCP and Azure. The code isn't perfect, but it should be a reasonable
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

!!! note

    The role assignment resource is `azurerm_role_assignment` and the `azurerm`
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

## A note on multi-tenancy

Amazon have [docs][apn] where they strongly advise tenant-specific OIDC issuer URLs
to avoid confused deputy attacks. I won't bother to repeat their explanation here,
but I'll add that I incorporated their advice into the sample code in the GitHub repo.

[cloudfed]: https://github.com/aidansteele/cloudfed
[apn]: https://apn-checklists.s3.amazonaws.com/foundational/partner-hosted/partner-hosted/CVLHEC5X7.html#technicalControls-cross-AccountAccess
