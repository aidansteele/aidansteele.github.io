---
layout: post
title: AWS IAM OIDC IDPs need more controls
date:
  created: 2021-10-12T03:58:52
categories:
  - AWS
---

<!-- more -->

## Background primer

In my post [_AWS federation comes to GitHub Actions_][previous-post] I wrote about 
GitHub Actions' new ability to federate access into AWS (and other clouds) via
OpenID Connect. This is really great, much better than the prior state of affairs,
but needs improvement on the AWS side.

Today, AWS IAM OIDC identity providers have a few configuration options:

* URL: this is specified at OIDC IDP creation time, immutable and must be unique
  on a per-AWS account basis. Corresponds to the `iss` claim in OIDC tokens.

* Client ID list: this is specified at creation time, but also mutable and can
  added to or removed from after the fact. Corresponds to the `aud` claim in
  OIDC tokens.

* Thumbprint list: this is specified at creation time and can be updated after 
  the fact. This is a security measure to ensure that MITM attacks between AWS
  and the IDP cannot occur, nor can an attacker register an expired IDP domain
  and gain access to your account.

* Tags: mutable, not super interesting as the functionality is free and there
  are only very rarely multiple OIDC IDPs in any given account.

The above is the full extent of what exists today. I think it's insufficient,
especially in light of the wide interest in GitHub Actions' support and EKS'
(AWS hosted Kubernetes service) dependence on OIDC.

## My requests

### Centralised control and guardrails

In the previous blog post, I shared an example CloudFormation template for
using the GHA OIDC feature. It looks like this:

![trust policy important condition](/assets/2021-10-12-trust-condition.png)

I have highlighted the most important part of the template. When this blog post
was first published, that condition was technically optional (in the sense that 
everything will work without it) but devastating if it was omitted. **It is the 
only thing that controls which repositories on GitHub are authorised to assume 
this role.** (GitHub allows configuration of the `aud` claim, so the `ClientIdList` 
property of the OIDC  IDP is not a security control.) Since then, AWS has made
the condition mandatory. Scott Piper over at Wiz has a [great write-up][wiz-update]
on the happy ending.

Many AWS customers now allow developers to freely create IAM roles, thanks to
[permission boundaries][boundaries]. There is no analogue to permission boundaries
for role trust policies - so once the GitHub IDP exists in an account, 
administrators have no way to enforce that it can only be used by particular
GitHub orgs. 

The same problem exists for Kubernetes: once the IDP exists in an account,
there is no way for administrators to enforce that roles in that account
can only be used by particular Kubernetes namespaces.

**Request**: something equivalent to permission boundaries for role trust policies.
Really, anything. It could be "trust policy boundary" policies that are attached
to individual roles with conditions mandating attachment in `iam:CreateRole`
and `iam:UpdateAssumeRolePolicy`. Or it could be policies that are attached
to the OIDC IDP IAM object itself. I haven't thought about which is preferable,
but _something_ is needed.

### Claim-to-tag mappings

**Update**: This doesn't exist in _AWS IAM_ yet, but it can be achieved via
AWS Cognito. I wrote a [follow-up blog post][follow-up] that explains how
to achieve it.

AWS IAM has supported role session tags for a while now. Have you ever looked
at how they work for roles bootstraped from OIDC IDPs? Here's what needs to
go in the JWT issued by the IDP:

![oidc token session tags](/assets/2021-10-12-session-tags.png)

Do you ever see GitHub Actions supporting this? Or any social network? Or
GitLab? Not even AWS EKS vends ID tokens with this claim namespace. I can't
think of any use case for this design. If you have that much control over
the format of the JWTs, you're probably issuing them yourself. In which case,
why not assume a role directly? Anyway, I digress.

**Request**: Give me a way to map arbitrary claims from the OIDC token to
role session tags in AWS. The tokens issued by GitHub have some extremely
useful information and I want to use it in my policies. I also want those
values to appear in CloudTrail. Hell, they should be usable in the above request
for trust policy boundaries: maybe roles should only be assumable for 
workflows initiated by `aidansteele`. 

Again, these could be configured on either a per-role basis or as a property
of the OIDC IDP object. I'm erring towards the latter in this case. It's the
kind of thing you want consistency in. And again, this would be useful for EKS.

## Wrap up

AWS is customer-obsessed, but not silly. They're not going to build this
functionality just because I asked for it. But they use demand to prioritise
work. I would encourage you to file a feature request ticket with the IAM team
adding your +1 to the ask. Here's an example that you definitely shouldn't
use.

![oidc token session tags](/assets/2021-10-12-feature-request.png)

[previous-post]: /blog/2021/09/15/aws-federation-comes-to-github-actions.html
[boundaries]: https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_boundaries.html
[follow-up]: https://awsteele.com/blog/2023/10/25/aws-role-session-tags-for-github-actions.html
[wiz-update]: https://www.wiz.io/blog/a-security-community-success-story-of-mitigating-a-misconfiguration
