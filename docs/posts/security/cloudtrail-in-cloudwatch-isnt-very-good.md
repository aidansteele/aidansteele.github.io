---
layout: post
title: CloudTrail in CloudWatch isn't very good
date:
  created: 2026-06-19T04:08:00
categories:
  - AWS
---

Amazon has deprecated CloudTrail Lake as of 1st June 2026 for new customers. I
assume this is due to lack of uptake. I never got around to properly using it,
and I'm a CloudTrail fan! So I can only imagine not many others used it. In its
place, Amazon [recommends][ct-doc] that we "explore CloudWatch". I explored
CloudWatch and came away quite disappointed.

<!-- more -->

Let me start with my hopes and dreams on setting this up. I had heard that
CloudWatch had some shiny new "unified data store". This unified data store can
be queried using S3 Tables, i.e. Athena will be able to query it efficiently.
This sounded great, because the biggest pain point with querying regular CloudTrail
trails using Athena is the sprawl of too many small files and maintaining dynamic
partitioning configuration. Having all this automatically managed is very valuable.
I was also excited to be able to try out the new enriched context that was
previously only available in CloudTrail Lake (more on that in a bit).

Let's look at the [docs][ct-doc]. Specifically, Amazon says:

> We recommend that you migrate your AWS CloudTrail Lake logs data to Amazon
> CloudWatch.

and

> Amazon CloudWatch provides the current capabilities of CloudTrail Lake at a
> comparable price point, and has additional capabilities [...]

I'll say up front: this is not the case. The docs say that CloudTrail Lake had
"limited" data transformation and enrichment, compared to "yes" for CloudWatch.
This is true in the general case, but CloudWatch is missing one of the most
interesting enrichment options that Lake had: the ability to enrich events with
[resource tags and global condition keys][enrichment]. That functionality alone
is the reason I was hoping to move to Lake in the past. Is it coming to
CloudWatch? To trails stored in S3? No idea, but hopefully.

But that's not even the worst part. The worst part is how difficult it is to
enable the CloudTrail -> CloudWatch ingestion. I don't think I'm particularly
dumb. In fact, I enabled CloudTrail -> CloudWatch ingestion (the "old" way)
in my personal AWS org over 10 years ago. And yet it took me a few hours and
$50 worth of AI credits to figure out how to get this new integration working.
If I can't figure out how to do this, what chance do most well-adjusted AWS
customers have?

!!! note "Am I crazy?"
    Try it yourself: try googling for how to enable CloudTrail -> CloudWatch
    ingestion. If it mentions a "trail", it's not what you want - that's the
    old way. If it mentions a "service-linked channel", that's right - and I
    want to know what docs/blogs you found, because I certainly couldn't find it.

I'll spare you the details, here are the highlights:

* There's actually nothing that needs to be done on the CloudTrail side. It all
  happens on the CloudWatch side. No trails needed.
* You need to enable organisation trusted access for CloudWatch via the
  `StartTelemetryEvaluationForOrganization` API.
* An organisation-level CloudTrail trail applies to the whole organisation. But
  an organisation-level enablement rule for CloudTrail in CloudWatch only applies
  to all _member_ accounts - it doesn't apply to the management account. This is
  consistent with other AWS services, but inconsistent with CloudTrail. The only
  clue that this is the case is the fact that [this doc][cw-doc] mentions an
  "SLC path" (I happened to know this stood for service-linked channel) and that
  no service-linked channel was created in the org management account.
* That means you need to create at least two resources: an org-level rule and
  an account-level rule for the management account.
* It took ~8 hours after creating an org-level enablement rule before events
  started flowing into my CloudWatch log groups. The docs _do_ say it can take
  up to 24 hours, but this was still surprising in my tiny personal org. A trail
  only takes minutes before the events start flowing.
* When the events start flowing, you realise that it just enables events to be
  sent to log groups in each AWS account. They're not centralised! For that,
  you need to create a separate "log centralisation rule". And that requires
  a service-linked role to be created in the target account.
* You need to enable CloudWatch<->S3 Tables integration, it's not automatic.
* Once you've enabled centralisation, you probably want to reduce the retention
  on log groups in each of the member accounts. I tried doing this twice on two
  separate days, and kept getting `InternalServerException` when calling the
  `UpdateTelemetryRuleForOrganization` API.
* Even if you look past all this, it is hard to calculate how cost-effective
  this is compared to using CloudTrail trails. Data events for trails are charged
  per-event. CloudWatch charges per ingested gigabyte. Which is cheaper? I'm
  not sure. I'll look into that in a follow-up post.

All in all, it feels pretty half-baked. I found no blog post from AWS on how
to set this up, I found no docs on either the CloudTrail or CloudWatch side on
how to set up the equivalent of CloudTrail Lake, and I found no third-party
blog posts on it either. Given that updating the retention failed, I wonder
if this new functionality is even less-used than CloudTrail Lake was.

I expect that it will get better with time, as most AWS services do. But this
was released with less polish than most AWS services are, so maybe that hope
is misplaced. Time will tell. In any case, I've [published the Terraform][my-tf]
my agent generated in order to get this all working.

[ct-doc]: https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-lake-service-availability-change.html
[enrichment]: https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-context-events.html
[my-tf]: https://github.com/aidansteele/cloudtrail-cloudwatch-2026
[cw-doc]: https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/telemetry-config-rules.html
