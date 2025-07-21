---
layout: post
title: Improve GitHub Actions OIDC security posture with custom issuer
date:
  created: 2023-01-11T03:30:52
categories:
  - AWS
---

<!-- more -->

GitHub Actions has supported using OIDC tokens for about 15 months now. It is
a much better way of providing AWS credentials to workflows than creating IAM users
and storing long-lived access keys in GitHub Actions secrets.

One issue holding back larger organisations from adopting this solution is the
lack of useful granular controls. I touched on this in an earlier article [_AWS IAM OIDC IDPs need more controls_][earlier].

I've since seen a new section pop up in the GitHub docs: [_Switching to a unique token URL_][docs].
It was actually [announced][announcement] back in August 2022 but I either didn't 
see it or missed the significance.

GitHub Enterprise Cloud customers can now get OIDC tokens issued that look like 
this (trimmed for brevity):

```json
{
  "iss": "https://token.actions.githubusercontent.com/octocat-inc",
  "jti": "6f4762ed-0758-4ccb-808d-ee3af5d723a8",
  "sub": "repo:octocat-inc/private-server:ref:refs/heads/main",
  "aud": "http://octocat-inc.example/octocat-inc",
  "enterprise": "octocat-inc",
  "bf": 1755350653,
  "exp": 1755351553,
  "iat": 1755351253
}
```

The relevant field is the `iss` (issuer) on the first line. If your enterprise 
slug is `octocat-inc` like in this example, you can now create an IAM OIDC IdP
with the following CloudFormation:

```yaml
  GithubOidc:
    Type: AWS::IAM::OIDCProvider
    Properties:
      Url: https://token.actions.githubusercontent.com/octocat-inc
      ThumbprintList: [6938fd4d98bab03faadb97b34396831e3780aea1]
      ClientIdList: [sts.amazonaws.com]
```

and you create a role for GitHub Actions to assume with this:

```yaml
  Role:
    Type: AWS::IAM::Role
    Properties:
      RoleName: ExampleGithubRole
      ManagedPolicyArns: [arn:aws:iam::aws:policy/ReadOnlyAccess]
      AssumeRolePolicyDocument:
        Statement:
          - Effect: Allow
            Action: sts:AssumeRoleWithWebIdentity
            Principal:
              # this line horizontally scrolls. 
              # the important part is on the end!
              Federated: !Sub arn:aws:iam::${AWS::AccountId}:oidc-provider/token.actions.githubusercontent.com/octocat-inc
            Condition:
              StringLike:
                token.actions.githubusercontent.com:sub: !Sub repo:your-org/your-repo:*
```

## Significance

Note that the ARN of the federated IAM IdP includes the enterprise name. You 
should still create roles with conditions on the `sub`, but **it is not 
catastrophic if you don't**. You can grant developers permission to invoke 
`iam:CreateRole` without worrying that an errant role trust policy has opened 
up access to the entirety of Github.com (a missing condition "only" opens up
access to any repository in _your enterprise_)

## Conclusion

I'd still like to see the AWS IAM controls mentioned in the earlier blog post
and I'd still like a way to see the full JWT claims in CloudTrail, but this
is a really nice improvement that will enable usage of this functionality for
more conservative organisations.

[earlier]: https://awsteele.com/blog/2021/10/12/aws-iam-oidc-idps-need-more-controls.html
[docs]: https://docs.github.com/en/enterprise-cloud@latest/actions/deployment/security-hardening-your-deployments/about-security-hardening-with-openid-connect#switching-to-a-unique-token-url
[announcement]: https://github.blog/changelog/2022-08-23-github-actions-enhancements-to-openid-connect-support-to-enable-secure-cloud-deployments-at-scale/
