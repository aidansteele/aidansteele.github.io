---
layout: post
title: "CloudTrail wishlist: filtering by principal ARN"
date: 2024-11-09 14:57:00 +1100
categories: blog
---

**UPDATE**: My dream came true - almost. See follow-up [post][follow-up].

AWS re:Invent 2024 is fast approaching and there's usually a flurry of exciting
new services and features for existing services launched around this time each
year. I'll be there in person this year - come say hello if you are too!

AWS CloudTrail is one of the services I rely on most. I probably run SQL queries
against CloudTrail events at least ten times a week. It's useful for so much 
more than just auditing: when a developer writes on Slack "my app can't access
an object in bucket xyz", I usually jump into CloudTrail to find out what AWS
account they're using, which IAM role in that account, what API are they using,
etc. It's great.

There's only one problem with CloudTrail: it can get expensive when you turn on
all the functionality. Data events (i.e. things like reading objects in S3, DynamoDB,
etc) cost $1 per million events - that's (significantly) more expensive than 
the actual API call itself. This makes it hard to justify enabling data-level
events when 99% of events are "boring" (i.e. applications doing what they're
designed to do). That's where my wishlist for a re:Invent launch comes in:

I wish I could specify an [advanced event selector][doc] filter on my trails to 
the effect of "only log (S3|DynamoDB|Kinesis|etc) data-level events if the principal 
ARN does not match `arn:aws:iam::*:role/service-role/*`". This would allow me 
to have an audit trail of atypical access (e.g. a developer downloading an object 
as part of debugging), while cutting out 99% of the noise - and therefore cost.

[follow-up]: /blog/2025/05/07/cloudtrail-wish-almost-granted.html
[doc]: https://docs.aws.amazon.com/awscloudtrail/latest/APIReference/API_AdvancedEventSelector.html
