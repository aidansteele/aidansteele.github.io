---
layout: post
title: OIDC tokens can now restrict which AWS roles they assume
date:
  created: 2026-07-13T11:30:00
categories:
  - AWS
  - OIDC
---

`AssumeRoleWithWebIdentity` seems to have a new, barely-documented, policy
condition key. It's called `sts:RoleAuthorizedByIdp` and if you're anything like
me (my condolences), that name will pique your interest. It's not super useful
*today* (unless you're running an OIDC IdP), but its utility will grow as adoption 
improves over time. So here's what I've learned so far.

<!-- more -->

## The claim

Today, the official [documentation][docs] says:

> Filters access based on whether the identity provider authorized the role 
> via the roles claim in the OIDC token

That's not a lot to go on. After some trial and error, I discovered that the
new claim follows the naming scheme established by tags and source identity, i.e.
it looks like this:

```json
{
  "iss": "https://idp.example.com",
  "sub": "poc-user",
  "aud": "sts.amazonaws.com",
  "iat": 1783904100,
  "exp": 1783904700,
  "https://aws.amazon.com/roles": "arn:aws:iam::111122223333:role/ExampleRole"
}
```

The claim can also be an array:

```json
{
  "https://aws.amazon.com/roles": [
    "arn:aws:iam::111122223333:role/RoleA",
    "arn:aws:iam::111122223333:role/RoleB"
  ]
}
```

When this token is passed to [`AssumeRoleWithWebIdentity`][arwwi], STS checks
that the requested role ARN exactly matches the string, or at least one value
in the array. If it doesn't, STS returns this surprisingly helpful error:

```
InvalidIdentityToken: The target role ARN is not present in the roles claim of the identity token
```

This happens **before** the role trust policy can allow the request. I tested this
by putting the ARN of role X in the token and using it to request credentials
for role Y. Role Y's trust policy allowed the token's issuer, audience and subject,
and didn't use the new condition key at all. STS still rejected it.

This means the claim isn't just extra context that can optionally be used by a
trust policy. Once present, it is enforced by STS itself as an allow-list of roles. 
The value has to be a literal ARN, or an array of ARNs. It can't be a role name, 
it can't include wildcards.

## Why is this useful?

Back in 2021 I wrote that [AWS IAM OIDC IDPs need more controls][idp-controls].
Since then, some of those problems have been solved by resource control policies 
(RCPs). Those are very useful, and realistically probably more useful than this
new feature in most scenarios. But this feature gives the IdP a say in the
decision - and a chance to emit useful audit logs. Consider two roles that 
accidentally share this trust policy:

```yaml
StringEquals:
  idp.example.com:aud: sts.amazonaws.com
  idp.example.com:sub: deployment-service
```

One is a development deployment role and the other is a production admin role.
Without the new claim, a compromised deployment service can request an OIDC token,
change the `RoleArn` argument sent to STS, and try the production role. Both roles
see the same valid `iss`, `aud` and `sub` values.

If the IdP puts only the development role ARN in `https://aws.amazon.com/roles`,
the production request would fail even though its trust policy is too broad. If the
production role also requires `sts:RoleAuthorizedByIdp`, a token that omits the
claim fails too.

You could already achieve the same theoretical result by issuing a unique `sub`
or `aud` for every role, then correctly checking it in every role trust policy.
That's sort of how a lot of OIDC IdPs work today, by bundling a lot of values
into one long `sub` value. Encoding a role ARN in a dedicated claim is much clearer,
and direct STS enforcement provides defence in depth when a target role's trust
policy is wrong.

This is particularly useful for SaaS vendors that issue tokens for roles across 
many AWS accounts, e.g. CI/CD providers or security scanners. The IdP can put the 
exact role ARN in the token, and cryptographically bind that decision to the 
token - then no matter how misconfigured their customers' setups are, the token 
can't be misused. It also gives the IdP a chance to log which target role an 
OIDC token was intended for. This is pretty useful and easy to do, because I 
guess most tokens are issued on-demand.

## Making it mandatory

Say you're an enthusiastic cloud security engineer and it's some point in the 
future. You love this new functionality, your IdPs all support it and you want 
to make it mandatory, i.e. you want to reject any OIDC tokens without the new
claim. This is where `sts:RoleAuthorizedByIdp` comes in. It is a boolean condition 
key that is `true` when the requested role ARN is present in the namespaced claim.
A trust policy can require role-bound tokens like this:

```yaml
Effect: Allow
Action: sts:AssumeRoleWithWebIdentity
Principal:
  Federated: arn:aws:iam::111122223333:oidc-provider/idp.example.com
Condition:
  StringEquals:
    idp.example.com:aud: sts.amazonaws.com
    idp.example.com:sub: poc-user
  Bool:
    sts:RoleAuthorizedByIdp: "true"
```

This means that if idp.example.com is misconfigured and emits an OIDC token
*without* the new claim it will be rejected, even if the `aud` and `sub` claims 
are correct. That's a nice defence-in-depth measure and genuinely useful, because 
I suspect that these role-bound tokens will always be an optional feature, and 
not every developer/agent in your company will always remember to enable them
when they're working on their GitHub Actions pipelines, for example. This
condition key also works in RCPs - and I imagine that will be a better place
to enforce it, e.g. this makes it mandatory everywhere

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Deny",
    "Principal": "*",
    "Action": "sts:AssumeRoleWithWebIdentity",
    "Resource": "*",
    "Condition": {
      "ArnLike": {
        "aws:FederatedProvider": "arn:aws:iam::*:oidc-provider/idp.example.com"
      },
      "Bool": {
        "sts:RoleAuthorizedByIdp": "false"
      }
    }
  }]
}
```

## CloudTrail

Successful role-authorised assumptions get a new field in `additionalEventData`:

```json
{
  "additionalEventData": {
    "ExtendedRequestId": "...",
    "RequestDetails": {
      "awsServingRegion": "ap-southeast-2",
      "endpointType": "regional"
    },
    "RoleAuthorizedByIdp": true,
    "identityProviderConnectionVerificationMethod": "IAMTrustStore"
  }
}
```

A successful request made with a token that doesn't have the claim simply omits
`RoleAuthorizedByIdp`; it doesn't log `false`. This is a path fairly well-trodden
by AWS, e.g. `aclRequired` or `explicitTrustGrant`.

## Vendor support

I validated all of the above by testing with a home-grown OIDC IdP. That's all 
well and good, but most of us don't run our own OIDC IdPs for real workloads.
This feature is only as useful as its breadth of support, and right now I assume
that exactly zero vendors support it. My guess is that AWS is working behind the 
scenes with the biggest sources of OIDC role assumption (GitHub, GitLab, BuildKite, 
GCP, etc) to get them to support this new functionality and then they'll co-launch 
some blog posts about it. If it's not too late, I have a request for those vendors: 
**please include the role ARN in "OIDC token created" events in your audit logs**. 
That will be extremely helpful, and absolutely make my day.

[docs]: https://docs.aws.amazon.com/service-authorization/latest/reference/list_sts.html
[arwwi]: https://docs.aws.amazon.com/STS/latest/APIReference/API_AssumeRoleWithWebIdentity.html
[idp-controls]: /blog/2021/10/12/aws-iam-oidc-idps-need-more-controls.html
