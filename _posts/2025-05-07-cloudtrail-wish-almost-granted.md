---
layout: post
title: "CloudTrail wish: almost granted"
date: 2025-05-07 10:50:00 +1000
categories: blog
---

Back in November last year, I [wished][prev-blog] for the ability to filter 
CloudTrail data events by the requesting principal's ARN. Two days later, my wish
was almost granted: CloudTrail launched the ability to filter on `userIdentity.arn`
for CloudTrail _lakes_ but not _trails_. And now it seems my wish has almost
completely come true: the functionality has rolled out to trails as well.

I say "almost" because it comes with a few caveats. I wished for a way to filter
on the principal's ARN, i.e. the field at `userIdentity.sessionContext.sessionIssuer.arn`.
We can only filter on `userIdentity.arn`. These are mostly similar, but the latter
drops the path (if any exists) on the IAM user/role. That's a shame if you've
neatly categorised all your human-assumable IAM roles under a `/human/` path and
hoped to only log their access to DynamoDB, S3, etc. Instead you have to hope
that you are also using a pattern on the role _name_ and match based on that.

That leads me to the second caveat: you can match on string prefixes and/or 
suffixes and use negation, but there is no pattern-matching. If you are using an
organization-level trail and want to log all DynamoDB writes by a role called `admin`,
I can't see how to do that. You can't match on `arn:aws:sts::*:assumed-role/admin`.
You can't use a suffix match on `assumed-role/admin` because the `userIdentity.arn`
field also includes the role session name (which is often an email address, a timestamp
or a random string). That makes it signficantly less useful if you have a lot
of AWS accounts.

The CloudTrail console has an example _Exclude AWS service-initiated events_ 
event selector, and it generates the following JSON. Notably the negated prefix
match has a role session ARN **without** an account ID. I tried following this
pattern and it didn't work. An event selector with an account ID _did_ match.

![screenshot](/assets/2025-05-07-console.png)

I hope I'm missing something here, because this limits the utility of the new
functionality in my eyes. Please reach out if so!

[prev-blog]: /blog/2024/11/09/cloudtrail-wishlist.html
