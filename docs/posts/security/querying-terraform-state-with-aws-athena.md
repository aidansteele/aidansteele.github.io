---
layout: post
title: Querying Terraform state with AWS Athena
date:
  created: 2025-10-26T17:06:52
categories:
  - AWS
---

Athena is one of my favourite AWS services. Though it's marketed as a big data
service, it is useful in many other scenarios. Sometimes I use it as a "grep
through unstructured logs in S3" and other times I use it to query CloudTrail 
logs - but this latter use case is likely better served by CloudTrail Lake 
nowadays. Today, I'll show how it can be used for querying Terraform state
stored in S3.

<!-- more -->

S3 is probably the most common place for storing Terraform state (source: I
made it up). A common pattern is to store all state for all stacks across an
AWS organisation in a single bucket. This makes it easy for a central ops/security
team to lock down and audit access to the bucket, ensure it is backed up 
correctly, etc. Sometimes those central teams have questions like "what providers
are developers using?" or "how many instances of `aws_s3_bucket_versioning` are
deployed across my org?" Those questions can be easily answered via Athena
queries against that central bucket.

Step one is creating a table in Athena. Note that this doesn't actually write 
any data to S3, it's just metadata that Athena uses to locate and parse the data
it finds in an S3 bucket. 

The table can be created using this Athena query:
```sql
CREATE EXTERNAL TABLE terraform_state(
  version int, 
  terraform_version string, 
  serial int, 
  lineage string, 
  outputs map<string,string>, 
  resources array<
    struct<
      module:string,
      mode:string,
      type:string,
      name:string,
      provider:string,
      instances:array<
        struct<
          schema_version:int,
          attributes:string,
          identity_schema_version:int,
          private:string,
          dependencies:array<string>
        >
      >
    >
  >
)
STORED AS ION
LOCATION 's3://your-s3-bucket-name-here/'
```

Note that we use the [Amazon Ion serde][ion]. This is because Terraform state
files are pretty-printed JSON - which is a subset of valid Ion files. The other
JSON-specific serdes in Athena don't support pretty-printed (multi-line) JSON.

Now the fun part: querying it. First, a basic query to demonstrate the kind
of data we're working with:

```sql
SELECT 
"$path",
split("$path", '/')[4] as accountId,
split("$path", '/')[5] as stack,
terraform_version,
outputs,
r.module,
r.mode,
r.type,
r.name,
r.provider,
i.attributes,
i.dependencies
FROM terraform_state
CROSS JOIN unnest(resources) AS _(r)
CROSS JOIN unnest(r.instances) AS _(i)
```

Some points to note, in no particular order:

* The path to my Terraform state across my org is always 
  `${accountId}/${stack}/terraform.tfstate`. If yours isn't, you can delete the
  second and third columns.
* The cross joins exist because Terraform state files exist as nested JSON arrays.
  I mostly care about instances of Terraform resources, and I suspect you do too.
* There are some fields declared in the `CREATE TABLE` that I didn't reference
  here. There's a small chance you might find them useful, but I didn't.

Now what kind of useful queries can we write with this? That's where I'm hoping
others can pitch in: please get in touch via Twitter, Bluesky, Slack, etc and
let me know what you come up with.  

Here's one to get started: find every
instance where you're one refactor away from a bad time:

```sql
SELECT 
split("$path", '/')[4] as accountId,
split("$path", '/')[5] as stack,
r.module,
r.name
FROM terraform_state
cross join unnest(resources) as _(r)
cross join unnest(r.instances) as _(i)
where r.type = 'aws_iam_policy_attachment'
```

[ion]: https://docs.aws.amazon.com/athena/latest/ug/ion-serde.html
