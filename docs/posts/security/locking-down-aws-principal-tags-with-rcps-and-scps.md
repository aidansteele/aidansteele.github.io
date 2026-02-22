---
layout: post
title: Locking down AWS principal tags with RCPs and SCPs
date:
  created: 2026-02-21T03:08:00
categories:
  - AWS
---

AWS principal tags are useful for fine-grained access control. As an organisation
administrator, you can craft service control policies (SCPs) that only allow 
tagged roles to call sensitive APIs. The problem then becomes: how do you guarantee 
that the tags are legitimate? This is where resource control policies (RCPs) come 
in handy - I provide a demonstration of them in this blog post, and an example of 
what you can achieve with the trustworthy tags in place.

<!-- more -->

## The problem

I'll lay out a scenario. You run a large AWS organisation. You give your 
development teams a lot of autonomy: each service gets its own AWS accounts,
and the development team for each service effectively has admin-level access in 
their respective accounts. This allows them to ship quickly, and not get slowed
down by a central IAM team that has to approve (or worse yet: deploy themselves)
all IAM changes. 

This works well, but in practice not every developer on every team is going to 
be an AWS expert with years of experience avoiding gotchas. Or they're under
time pressure and take shortcuts. Or maybe they just have a lazy AI agent who
wants to get the job done quickly and go back to sleep. So you need to lock
_some_ things down. Like long-lived credentials.

Long-lived credentials are a common audit finding. They're hard to keep track of,
but difficult to eliminate entirely. So you want to allow _some_ teams in your 
organisation to create access keys, but not all. You might decide to use tags 
to do that. Your SCP will look something like this:

```yaml
- Sid: DenyLongTermCredentialCreation
  Effect: Deny
  Action:
    - iam:CreateAccessKey
    - iam:UpdateAccessKey
    - iam:CreateLoginProfile
    - iam:UpdateLoginProfile
    - iam:CreateServiceSpecificCredential
  Resource: "*"
  Condition:
    StringNotEquals:
      aws:PrincipalTag/scp-exempt-access-keys: "true"
```

Most principals won't have this tag, so they'll be denied. But out of the box,
any of your development teams can add those tags to a role (because you've given
them admin access!)

## A partial solution

So you decide that only a `tagger` role can apply those tags. So you roll out a 
`tagger` role everywhere (presumably using CloudFormation service-managed stack 
sets), and follow it up with this SCP statement:

```yaml
- Sid: DenyIAMPrincipalTagging
  Effect: Deny
  Action:
    - iam:TagRole
    - iam:TagUser
    - iam:UntagRole
    - iam:UntagUser
    - iam:CreateRole
    - iam:CreateUser
  Resource: "*"
  Condition:
    ForAnyValue:StringLike:
      aws:TagKeys: "scp-*"
    StringNotLike:
      aws:PrincipalArn: arn:aws:iam::*:role/tagger
```

Great, now we're a bit closer. Only the organisation administrator can assume the
`tagger` role and hand out `scp-exempt-access-keys=true` tags to `admin` roles in
member AWS accounts.

## Session tags

...but resource tags on roles and users aren't the only place that principal tags
can come from. Principal tags are the union of the principal resource tags and 
session tags, so you need to lock down session tags too. This is where RCPs 
come in. 

Why RCPs? Because SCPs only apply to principals in your organisation - and session
tags can come from outside your organisation. Think cross-account role assumption
from SaaS vendors, think OIDC and SAML identity providers. RCPs [launched][rcp-launch] 
in November 2024 and solved some of the problems I asked for in a previous 
[blog post][idp-controls].

RCPs provide a way to guarantee that `scp-*` session tags can only be applied to
principals in our organisation by the `tagger` role. Here's how:

```yaml
- Sid: DenySCPTagsNonTaggerRole
  Effect: Deny
  Principal: "*"
  Action: sts:TagSession
  Resource: "*"
  Condition:
    ForAnyValue:StringLike:
      aws:TagKeys: "scp-*"
    StringNotLike:
      aws:PrincipalArn: arn:aws:iam::*:role/tagger
- Sid: DenySCPTagsOutsideOrg
  Effect: Deny
  Principal: "*"
  Action: sts:TagSession
  Resource: "*"
  Condition:
    ForAnyValue:StringLike:
      aws:TagKeys: "scp-*"
    StringNotEquals:
      aws:ResourceOrgID: "${aws:PrincipalOrgID}"
```

The RCP needs two statements. A single combined statement won't work because 
conditions within a statement are ANDed, and we need OR logic: deny if the 
caller isn't the blessed role, **or** deny if the caller isn't in our org.

The second statement is important: without it, someone with a role named 
`tagger` in an account _outside_ your organisation could bypass the first 
statement. `StringNotEquals` on a missing key evaluates to `true` for negated 
operators, so this also blocks third-party accounts that aren't members of 
any org.

It might be interesting to note that OIDC and SAML IdPs are actually blocked by
the first statement. They have a principal, it's just a federated principal (i.e.
the one you see in your trust policy when you allow assumption by an IdP).

### Why two statements in the RCP?

I mentioned this above, but it's worth elaborating. If we combined the two 
conditions into a single statement:

```yaml
Condition:
  StringNotLike:
    aws:PrincipalArn: "arn:aws:iam::*:role/tagger"
  StringNotEquals:
    aws:ResourceOrgID: "${aws:PrincipalOrgID}"
```

Both conditions would need to be true for the deny to fire. This would leave 
two gaps:

- A `tagger` role **outside** your org → `StringNotLike` is false, deny 
  doesn't fire
- A non-tagger role **inside** your org → `StringNotEquals` is false, deny 
  doesn't fire

Two separate statements give us OR logic: either mismatch triggers a deny.

## Protecting the tagger role

Keen readers will note that there's nothing in these examples protecting the
`tagger` role. Indeed if we are giving our developers admin-level access, there's
nothing stopping them from editing this role so they can assume it themselves (if
it exists), or creating it in a way that suits them (if it doesn't). So we need
to lock that down too. 

How exactly you lock this down depends on how you deploy the role in the first
place. Despite their significant painpoints, I like using CloudFormation 
service-managed stacksets for this. It's an easy way to say "I want this role
to exist in every AWS account in my organisation" and leave it at that. The
stack (and therefore role) will be deployed as soon as a new AWS account is created,
which is well-suited for ensuring these security invariants. It also makes the
SCP fairly straightforward:

```yaml
- Sid: DenyModifyingPrivilegedRoles
  Effect: Deny
  Action:
    - iam:AttachRolePolicy
    - iam:CreateRole
    - iam:DeleteRole
    - iam:DeleteRolePermissionsBoundary
    - iam:DeleteRolePolicy
    - iam:DetachRolePolicy
    - iam:PutRolePermissionsBoundary
    - iam:PutRolePolicy
    - iam:TagRole
    - iam:UntagRole
    - iam:UpdateAssumeRolePolicy
    - iam:UpdateRole
    - iam:UpdateRoleDescription
  Resource: 
    - arn:aws:iam::*:role/tagger
    - arn:aws:iam::*:role/stacksets-exec-*
  Condition:
    StringNotLike:
      aws:PrincipalArn: arn:aws:iam::*:role/stacksets-exec-*
```

This prevents any principal other than the stackset execution role from creating
or modifying the `tagger` role. It is also necessary to protect the stackset
execution role itself from the same issue. Note that we don't need to exempt the 
`AWSServiceRoleForCloudFormationStackSetsOrgMember` service-linked role, because
service-linked roles are not subject to SCPs. 

## Some notes

- SCPs and RCPs don't apply to service-linked roles. I think that's okay, because
  I'm not aware of any service-linked roles that can assume (and provide session
  tags for) a role in your account. Let me know if I've missed something!
- You might be tempted to structure tags in a format like `scp-exemption=access-keys`.
  Technically this works, but I don't like it. I prefer to lock down a tag key
  prefix and use a tag key per "use case". Example use cases: You might have 
  teams that are allowed to create access keys and internet gateways, but not 
  public buckets. Other teams might only be allowed to create public buckets. Each
  of these three use cases should have their own tag.
- This is not a full ABAC strategy. How you might deal with matching tags on 
  principals and resources is a whole other blog post. Maybe I'll write it one
  day (if I can ever figure out a good way to do it.)
- Thank you to Adam Cotenoff, Stephanie Shi and Santosh Ananthakrishnan for 
  motivating me to write this post and then helping to improve it.

[rcp-launch]: https://aws.amazon.com/about-aws/whats-new/2024/11/resource-control-policies-restrict-access-aws-resources/
[idp-controls]: https://awsteele.com/blog/2021/10/12/aws-iam-oidc-idps-need-more-controls.html
