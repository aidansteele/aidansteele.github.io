---
layout: post
title: Reversing AWS IAM unique IDs
date: 2023-11-20 08:51:00 +1100
categories: blog
---

A few years ago, I [wrote][akia-blog] about determining AWS account IDs from AWS 
access keys, i.e. those strings that begin with `AKIA` or `ASIA`. It's also 
possible to determine information from other AWS IAM unique IDs, specifically 
these two from the table in [Amazon's docs][docs].

![screenshot](/assets/2023-11-20-docs-table.png)

These unique IDs can pop up in a few places, but the place I see them most often
is in CloudTrail logs when a principal in a different AWS account accesses a 
resource (like a KMS key or S3 bucket) in my account. In these situations, I often
want to know the ARN of the user/role, because it's easier to understand my logs.
As far as I know, the process for doing this is not documented and not well-known,
so here's a blog post on how to do it:

1. You have a unique ID. Let's say it's `AROAJMD24IEMKTX6BABJI` (that's a real ID
   you can use to follow this blog post)
2. Create or find an unused S3 bucket that you control. Add the following to its
   bucket policy:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Principal": {
           "AWS": "AROAJMD24IEMKTX6BABJI"
         },
         "Effect": "Deny",
         "Action": ["s3:GetObject"],
         "Resource": "arn:aws:s3:::YOUR_BUCKET_NAME_HERE/*"
       }
     ]
   }
   ```
3. Save the bucket policy.
4. Now view the bucket policy. You'll see that AWS has automatically resolved 
   the unique ID to the ARN of a role in my personal account:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Principal": {
           "AWS": "arn:aws:iam::607481581596:role/service-role/abctestrole"
         },
         "Effect": "Deny",
         "Action": ["s3:GetObject"],
         "Resource": "arn:aws:s3:::YOUR_BUCKET_NAME_HERE/*"
       }
     ]
   }
   ```   

There are a few things to know about this:

* Unique IDs only get resolved if they're in a `Principal` part of an AWS IAM 
  policy statement. They won't get affected if they're elsewhere, e.g. a `Condition`.
* It doesn't work for principals that have been deleted. If you try use a unique ID
  of a deleted principal, you get an `Invalid principal in policy` error when 
  you try to save the bucket policy.
* If you save this bucket policy on day 1 and I delete the role in my account on
  day 2, then when you look at the bucket policy again on day 3 it will revert
  to showing you the original unique ID. This is how you know I've deleted the
  role. Even if I recreate a role with the same name, it won't reappear - because
  the new role gets a new unique ID (this _is_ documented).

[akia-blog]: https://awsteele.com/blog/2020/09/26/aws-access-key-format.html
[docs]: https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_identifiers.html#identifiers-unique-ids
