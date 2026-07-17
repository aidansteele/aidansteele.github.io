---
layout: post
title: Filtering S3 events by CloudFormation stack
date:
  created: 2026-07-17T15:00:00
categories:
  - AWS
---

AWS just [announced][announcement] that S3 event notifications now include
the system-generated tags attached to the bucket responsible for the notification. 
This sounds like a small change, but it will enable some useful patterns. It's
also at least the third example of an AWS service offering value-add through
tag enrichment.

The release notes were a bit light on details, so I verified for myself what 
tags are (and more importantly: are _not_) included in events. I also want 
to take this as an opportunity to promote EventBridge for S3 object notifications,
as it's not used nearly enough.

<!-- more -->

## First, a pitch for S3 object notifications via EventBridge

This pattern is seriously underutilised. S3 object notifications are great,
but their management is tricky. Specifically, the object notification
configuration is a property of the bucket. That makes sense, but it has
annoying architectural implications. It makes a producer-consumer setup
annoying, because the producer needs to be aware of its consumer and where
it lives (which SQS queue, Lambda function, SNS topic, etc). Multiply the
annoyance when you have multiple consumers - the producer needs to know 
about all of them!

This is annoying but hard to get wrong when using CloudFormation, due to
the nature of the `AWS::S3::Bucket` resource. I've seen so many people
get it wrong with Terraform, though. Terraform models S3 notification
configuration as a top-level `aws_s3_bucket_notification` resource. This
makes it so easy to define the configuration alongside the consumer
instead of the producer. This _works_, but it's so fragile. The producer
might be in a different repo, oblivious to the fact that someone has
enabled notifications. Even worse, a second consumer might be oblivious to the
first consumer and define its own configuration - this overwrites the first
consumer! Disaster ensues. The Terraform [docs][tf] even call out this problem.

EventBridge is the solution. The producer does this:

```hcl
resource "aws_s3_bucket" "bucket" {
  bucket = "your-bucket-name"
}

resource "aws_s3_bucket_notification" "bucket_notification" {
  bucket = aws_s3_bucket.bucket.id
  eventbridge = true
}
```

That's it. Now it's clear to maintainers of the producer that there is at least
the _possibility_ of consumers. It's also clear there might be more than one. And 
most importantly, the producer doesn't need to know who those consumers are. This 
is (in my opinion) a *much* better fit for a typical microservices architecture
that you see nowadays. Even if you only ever have one consumer, and it's
defined in the same repo, you might as well use EventBridge. The costs are
minimal ($1 per million events) and it grants you trivial future-proofing
without any refactoring.

## A second digression: tag enrichment

First, CloudTrail Lake added support for [enriching events][lake] with the
tags of relevant resources. That is supremely useful for analysis: you can
easily search for all modifications to a particular set of buckets, for example.

Then, CloudWatch Logs added support for [enriching logs][cwl] with the tags
of the resources responsible for generating them. Combine this with CloudWatch
Log Insights and it became trivial to query all the logs for Lambda functions
defined in a given stack/application.

And based on [this release][flow], I expect a similar feature is coming soon
to flow logs. Whatever is going on, it seems there's a push within AWS to
"enrich all the things" with tag metadata and I am very happy about it. They've
been sitting on this goldmine of context and relying on us to build our own
pipelines to enrich it ourselves. I love pipeline plumbing as much as the next
AWS dork, but it's hard to argue this is not undifferentiated heavy lifting.

Now back to the new release today...

## What are system-generated tags?

The term "system-generated" tags jumped out at me a bit. What does that mean?
I verified that it means that S3 will only include a subset of tag key-value
pairs in object notifications. Specifically it will include tags whose keys
begin with `aws:` and not include any user-generated tags.

As best I can tell, there are three sources of such tags: CloudFormation, 
Service Catalog (which is just CloudFormation in a trench coat) and a weird
`aws:createdBy` billing thing. CloudFormation automatically adds these three 
tags to most resources that support tagging:

```text
aws:cloudformation:stack-id = arn:aws:cloudformation:...
aws:cloudformation:logical-id = SomeBucketResource
aws:cloudformation:stack-name = some-stack-name
```

I created an S3 bucket with CloudFormation, added a user-defined tag to the
resource, and passed another ordinary tag to the stack during deployment. A
`GetBucketTagging` call returned all five tags. The event notifications only
contained the three `aws:cloudformation:*` tags. This matches up with what AWS
said they would do, but I don't know why. It would have been so much more useful
if I could easily create a rule that says "match all object uploads from buckets
tagged `Service = user-files`!

## Native S3 notifications

I first configured a native S3 notification with an SQS queue as its destination,
then uploaded an object. The relevant part of the resulting message body looked
like this:

```json
{
  "Records": [
    {
      "eventVersion": "2.5",
      "eventName": "ObjectCreated:Put",
      "s3": {
        "bucket": {
          "name": "s3-system-tags-experiment-bucket-wletlbtdcbuc",
          "arn": "arn:aws:s3:::s3-system-tags-experiment-bucket-wletlbtdcbuc",
          "awsGeneratedTags": {
            "aws:cloudformation:stack-id": "arn:aws:cloudformation:ap-southeast-2:123456789012:stack/s3-system-tags-experiment/abc123",
            "aws:cloudformation:logical-id": "Bucket",
            "aws:cloudformation:stack-name": "s3-system-tags-experiment"
          }
        },
        "object": {
          "key": "direct-put.txt",
          "size": 14,
          "eTag": "518184f1449ab62320473984c5738d6a"
        }
      }
    }
  ]
}
```

The new field is `Records[].s3.bucket.awsGeneratedTags`. It's a map of tag keys
to values, rather than the array of `{Key, Value}` objects returned by many AWS
tagging APIs. The native S3 event schema has also been incremented to version
`2.5`.

## EventBridge notifications

I enabled EventBridge notifications on the same bucket and sent its events to a
second SQS queue. The EventBridge version of the event looked like this:

```json
{
  "detail-type": "Object Created",
  "source": "aws.s3",
  "detail": {
    "event-version": "1.1",
    "bucket": {
      "name": "s3-system-tags-experiment-bucket-wletlbtdcbuc",
      "aws-generated-tags": {
        "aws:cloudformation:stack-id": "arn:aws:cloudformation:ap-southeast-2:123456789012:stack/s3-system-tags-experiment/abc123",
        "aws:cloudformation:logical-id": "Bucket",
        "aws:cloudformation:stack-name": "s3-system-tags-experiment"
      }
    },
    "object": {
      "key": "direct-put.txt",
      "size": 14,
      "etag": "518184f1449ab62320473984c5738d6a"
    },
    "reason": "PutObject"
  }
}
```

Note the different naming convention. Native notifications use
`awsGeneratedTags`, while EventBridge uses `aws-generated-tags`. I don't
know why they would be inconsistent like this. It's tolerable, but annoying.

## Matching every bucket in a stack

The useful part is that EventBridge can have rules that match on just about
anything. For example: values inside the tag map. This CloudFormation rule 
matches object creation and deletion events from every EventBridge-enabled 
S3 bucket in the current stack:

```yaml
StackBucketEvents:
  Type: AWS::Events::Rule
  Properties:
    EventPattern:
      source:
        - aws.s3
      detail-type:
        - Object Created
        - Object Deleted
      detail:
        bucket:
          aws-generated-tags:
            'aws:cloudformation:stack-name': [!Ref AWS::StackName]
```

Each bucket still needs to have EventBridge notifications enabled. In
CloudFormation that looks like:

```yaml
NotificationConfiguration:
  EventBridgeConfiguration:
    EventBridgeEnabled: true
```

This seems particularly handy for generated bucket names, stacks containing
multiple buckets, and central rules deployed alongside application resources.
Previously the rule needed to know every physical bucket name. Now the
CloudFormation stack itself can be the unit of event routing.

[announcement]: https://aws.amazon.com/about-aws/whats-new/2026/07/amazon-s3-event-notifications-system-generated-tags/
[tf]: https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/s3_bucket_notification
[lake]: https://aws.amazon.com/blogs/mt/announcing-aws-cloudtrail-lake-now-supports-event-enrichment-add-business-context-to-your-aws-activity-logs/
[cwl]: https://aws.amazon.com/about-aws/whats-new/2026/06/amazon-cloudwatch-logs-resource-tags/
[flow]: https://aws.amazon.com/about-aws/whats-new/2026/07/amazon-cloudwatch-lookup-processor/