---
layout: post
title: AWS role session tags for GitHub Actions
date:
  created: 2023-10-25T01:24:00
categories:
  - AWS
---

<!-- more -->

Back in 2021, I [requested][my-blog] that AWS add some kind of "claim-to-tag mapping"
functionality to OIDC IDPs, so that we could have role session tags based on 
claims in OIDC tokens issued by GitHub Actions. That hasn't happened yet, but
today I learned (thanks to [this comment][comment] and associated [blog post][orig-blog]
by Daniel Jonsén) that the same outcome can be achieved by using AWS Cognito 
identity pools as an intermediary.

Cognito identity pools has [functionality][cognito-docs] that allows claims in
an OIDC token to be mapped to role session tags. On a simple level: once you've 
configured a dictionary of claim->tag mappings, you can give Cognito a GitHub 
OIDC token and it will return to you a Cognito-issued OIDC token with session 
tags. That Cognito OIDC token can then be used with `AssumeRoleWithWebIdentity`.

Here's how it works:

```yaml
# note that this cloudformation template assumes you have already created the github actions OIDC IdP in your account

Resources:
  IdentityPool:
    Type: AWS::Cognito::IdentityPool
    Properties:
      IdentityPoolName: gha-tags-example
      AllowClassicFlow: true # this is needed to allow direct AssumeRoleWithWebIdentity calls
      AllowUnauthenticatedIdentities: false
      OpenIdConnectProviderARNs:
        - !Sub arn:aws:iam::${AWS::AccountId}:oidc-provider/token.actions.githubusercontent.com

  TagMapping:
    Type: AWS::Cognito::IdentityPoolPrincipalTag
    Properties:
      IdentityPoolId: !Ref IdentityPool
      IdentityProviderName: !Sub arn:aws:iam::${AWS::AccountId}:oidc-provider/token.actions.githubusercontent.com
      UseDefaults: false
      PrincipalTags:
        actor: actor
        sha: sha
        run_id: run_id
        event: event_name # your tag can have a different name than the OIDC claim
        ref: ref
        repository: repository

  Role:
    Type: AWS::IAM::Role
    Properties:
      AssumeRolePolicyDocument:
        # this `Version` line is very important. conditions like the
        # role session name one below will fail without it
        Version: "2012-10-17"
        Statement:
          - Effect: Allow
            Action: sts:AssumeRoleWithWebIdentity
            Principal:
              Federated: cognito-identity.amazonaws.com # note that this is *NOT* the GHA url
            Condition:
              StringEquals:
                # this next condition is what stops cognito in *other* aws accounts from crafting
                # OIDC tokens for *your* account
                cognito-identity.amazonaws.com:aud: !Ref IdentityPool
                # this next condition is just an example of what's now possible. you don't 
                # actually need it, but it's handy for cloudtrail!
                sts:RoleSessionName: ${aws:RequestTag/run_id}@${aws:RequestTag/sha}
          - Effect: Allow
            Action: sts:TagSession
            Principal:
              Federated: cognito-identity.amazonaws.com
            Condition:
              StringEquals:
                cognito-identity.amazonaws.com:aud: !Ref IdentityPool

Outputs:
  IdentityPool:
    Value: !Ref IdentityPool
  Role:
    Value: !GetAtt Role.Arn
```

The process is now:

1. GHA workflow requests an OIDC token from GitHub Actions
2. GHA workflow calls [`cognito-identity:GetId`][api-getid] with original OIDC token and 
   is returned a Cognito "identity ID"
3. GHA workflow calls [`cognito-identity:GetOpenIdToken`][api-getoidc] with 
   original OIDC token and is returned a Cognito-issued OIDC token
4. GHA workflow calls [`sts:AssumeRoleWithWebIdentity`][api-arwwi] with Cognito-issued
   OIDC token and IAM role name ARN and is returrned temporary AWS credentials.

Steps 2 and 3 are new compared to the "standard process" and step 4 uses the 
Cognito-issued OIDC token instead of the GHA-issued OIDC token. Here's what the 
entry in CloudTrail looks like:

```json
{
  "eventVersion": "1.08",
  "userIdentity": {
    "type": "WebIdentityUser",
    "principalId": "cognito-identity.amazonaws.com:ap-southeast-2:14deebd0-19f8-4295-a55e-8b36e60b4926:ap-southeast-2:f33550b0-d103-4ff1-9319-1745fea988da",
    "userName": "ap-southeast-2:f33550b0-d103-4ff1-9319-1745fea988da",
    "identityProvider": "cognito-identity.amazonaws.com"
  },
  "eventTime": "2023-10-25T01:21:21Z",
  "eventSource": "sts.amazonaws.com",
  "eventName": "AssumeRoleWithWebIdentity",
  "awsRegion": "ap-southeast-2",
  "sourceIPAddress": "121.221.159.246",
  "userAgent": "aws-cli/2.13.28 Python/3.11.6 Darwin/23.0.0 source/arm64 prompt/off command/sts.assume-role-with-web-identity",
  "requestParameters": {
    "principalTags": {
      "actor": "aidansteele",
      "ref": "refs/heads/main",
      "run_id": "6634485805",
      "event": "workflow_dispatch",
      "repository": "ak2-au/oidc-token-fetcher",
      "sha": "65e4b17a18e0f86c7b608703ec4a8340c3461d01"
    },
    "roleArn": "arn:aws:iam::607481581596:role/gha-tags-test-Role-ZmTOykdCAhxs",
    "roleSessionName": "6634485805@65e4b17a18e0f86c7b608703ec4a8340c3461d01"
  },
  "responseElements": {
    "credentials": {
      "accessKeyId": "ASIAY24FZKAOEK7KVHCV",
      "sessionToken": "IQo<truncated>f+J+wQ=",
      "expiration": "Oct 25, 2023, 2:21:21 AM"
    },
    "subjectFromWebIdentityToken": "ap-southeast-2:f33550b0-d103-4ff1-9319-1745fea988da",
    "assumedRoleUser": {
      "assumedRoleId": "AROAY24FZKAOKXOMX4HDD:6634485805@65e4b17a18e0f86c7b608703ec4a8340c3461d01",
      "arn": "arn:aws:sts::607481581596:assumed-role/gha-tags-test-Role-ZmTOykdCAhxs/6634485805@65e4b17a18e0f86c7b608703ec4a8340c3461d01"
    },
    "packedPolicySize": 43,
    "provider": "cognito-identity.amazonaws.com",
    "audience": "ap-southeast-2:14deebd0-19f8-4295-a55e-8b36e60b4926"
  },
  "requestID": "a282953d-2752-442d-96b3-8d8bff4a73f3",
  "eventID": "824092dd-18ba-4a2f-8f94-8ada97a08dd4",
  "readOnly": true,
  "resources": [
    {
      "accountId": "607481581596",
      "type": "AWS::IAM::Role",
      "ARN": "arn:aws:iam::607481581596:role/gha-tags-test-Role-ZmTOykdCAhxs"
    }
  ],
  "eventType": "AwsApiCall",
  "managementEvent": true,
  "recipientAccountId": "607481581596",
  "eventCategory": "Management",
  "tlsDetails": {
    "tlsVersion": "TLSv1.2",
    "cipherSuite": "ECDHE-RSA-AES128-GCM-SHA256",
    "clientProvidedHostHeader": "sts.ap-southeast-2.amazonaws.com"
  }
}
```

Daniel has written a [GHA action][gha-action] that implements the aforementioned
process of requesting and exchanging OIDC tokens. 

## Bonus thoughts

Cognito identity pools has two different [authentication "flows"][flows] that 
are relevant to us. I used the "basic (classic) flow" above because it means we call
`AssumeRoleWithWebIdentity` directly (rather than Cognito doing it for us in the 
"enhanced" flow), which allows us to specify a role session name - this is useful
for CloudTrail attribution. It also allows us to specify the role ARN in the GHA
workflow itself, rather than in the Cognito configuration. This feels like it 
will be more familiar to administrators than the enhanced flow.

[my-blog]: https://awsteele.com/blog/2021/10/12/aws-iam-oidc-idps-need-more-controls.html
[comment]: https://github.com/aws-actions/configure-aws-credentials/issues/419#issuecomment-1777216106
[orig-blog]: https://catnekaise.github.io/github-actions-abac-aws/cognito-identity/
[cognito-docs]: https://docs.aws.amazon.com/cognito/latest/developerguide/attributes-for-access-control.html
[gha-action]: https://github.com/catnekaise/cognito-idpool-basic-auth
[api-getid]: https://docs.aws.amazon.com/goto/WebAPI/cognito-identity-2014-06-30/GetId
[api-getoidc]: https://docs.aws.amazon.com/goto/WebAPI/cognito-identity-2014-06-30/GetOpenIdToken
[api-arwwi]: https://docs.aws.amazon.com/goto/WebAPI/sts-2011-06-15/AssumeRoleWithWebIdentity
[flows]: https://docs.aws.amazon.com/cognito/latest/developerguide/authentication-flow.html
