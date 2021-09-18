---
layout: post
title: AWS federation comes to GitHub Actions
date: 2021-09-15 13:37:52 +1100
categories: blog
---

**At the time of writing, this functionality exists but has yet to be announced
or documented. It works, though!**

**EDIT**: Here is the functionality on the [GitHub roadmap][roadmap].

GitHub Actions has new functionality that can vend OpenID Connect credentials
to jobs running on the platform. This is very exciting for AWS account
administrators as it means that CI/CD jobs no longer need **any** long-term
secrets to be stored in GitHub. But enough of that, here's how it works:

First, an AWS IAM OIDC identity provider and an AWS IAM role that GitHub Actions
can assume. You can do that by deploying this CloudFormation template to your 
account.

```yaml
Parameters:
  RepoName:
    Type: String
    Default: aidansteele/aws-federation-github-actions

Resources:
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
              Federated: !Ref GithubOidc
            Condition:
              StringLike:
                vstoken.actions.githubusercontent.com:sub: !Sub repo:${RepoName}:*

  GithubOidc:
    Type: AWS::IAM::OIDCProvider
    Properties:
      Url: https://vstoken.actions.githubusercontent.com
      ThumbprintList: [a031c46782e6e6c662c2c87c76da9aa62ccabd8e]
      ClientIdList: 
        - !Sub https://github.com/${RepoName}

Outputs:
  Role:
    Value: !GetAtt Role.Arn      
```

Ok, this new role can now be assumed by GitHub Actions, but crucially: only by
jobs in my `aidansteele/aws-federation-github-actions` repo. Without that
condition, *any repo on GitHub* could assume this role.

Next, the GitHub workflow definition. Put this in a repo:

```yaml
# .github/workflows/example.yml
name: Example
on:
  push:

jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      id-token: write
      contents: read
    steps:
      - run: sleep 5 # there's still a race condition for now

      - name: Configure AWS
        run: |
          export AWS_ROLE_ARN=arn:aws:iam::0123456789012:role/ExampleGithubRole
          export AWS_WEB_IDENTITY_TOKEN_FILE=/tmp/awscreds
          export AWS_DEFAULT_REGION=us-east-1

          echo AWS_WEB_IDENTITY_TOKEN_FILE=$AWS_WEB_IDENTITY_TOKEN_FILE >> $GITHUB_ENV
          echo AWS_ROLE_ARN=$AWS_ROLE_ARN >> $GITHUB_ENV
          echo AWS_DEFAULT_REGION=$AWS_DEFAULT_REGION >> $GITHUB_ENV

          curl -H "Authorization: bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" "$ACTIONS_ID_TOKEN_REQUEST_URL" | jq -r '.value' > $AWS_WEB_IDENTITY_TOKEN_FILE

      - run: aws sts get-caller-identity # just an example. why not deploy something?
```

Tada, you now have a GitHub Actions workflow that assumes your role. It works
because the AWS SDKs (and AWS CLI) support using the `AWS_WEB_IDENTITY_TOKEN_FILE` 
and `AWS_ROLE_ARN` environment variables since [AWS EKS][eks] needed this.

## Some potential trust policies

Maybe you want an IAM role that can be assumed by any branch in any repo in your
GitHub org, e.g. with relatively few permissions needed for PRs. You can do this:

```yaml
Effect: Allow
Action: sts:AssumeRoleWithWebIdentity
Principal:
  Federated: !Ref GithubOidc
Condition:
  StringLike:
    vstoken.actions.githubusercontent.com:sub: repo:your-github-org/*
```

Maybe you want an IAM role scoped only to workflows on the `main` branches, because
this will be doing sensitive deployments. In that case, you can do:

```yaml
Effect: Allow
Action: sts:AssumeRoleWithWebIdentity
Principal:
  Federated: !Ref GithubOidc
Condition:
  StringLike:
    vstoken.actions.githubusercontent.com:sub: repo:your-github-org/*:ref:refs/heads/main
```

## FAQ

### What does the JWT look like?

```json
{
  "actor": "aidansteele",
  "aud": "https://github.com/aidansteele/aws-federation-github-actions",
  "base_ref": "",
  "event_name": "push",
  "exp": 1631672856,
  "head_ref": "",
  "iat": 1631672556,
  "iss": "https://vstoken.actions.githubusercontent.com",
  "job_workflow_ref": "aidansteele/aws-federation-github-actions/.github/workflows/test.yml@refs/heads/main",
  "jti": "8ea8373e-0f9d-489d-a480-ac37deexample",
  "nbf": 1631671956,
  "ref": "refs/heads/main",
  "ref_type": "branch",
  "repository": "aidansteele/aws-federation-github-actions",
  "repository_owner": "aidansteele",
  "run_attempt": "1",
  "run_id": "1235992580",
  "run_number": "5",
  "sha": "bf96275471e83ff04ce5c8eb515c04a75d43f854",
  "sub": "repo:aidansteele/aws-federation-github-actions:ref:refs/heads/main",
  "workflow": "CI"
}
```

### And the CloudTrail entry?

```json
{
  "awsRegion": "us-east-1",
  "eventCategory": "Management",
  "eventID": "096c33c2-7d1d-49c6-a87b-fb4bbb5d43d6",
  "eventName": "AssumeRoleWithWebIdentity",
  "eventSource": "sts.amazonaws.com",
  "eventTime": "2021-09-15T03:00:36Z",
  "eventType": "AwsApiCall",
  "eventVersion": "1.08",
  "managementEvent": true,
  "readOnly": true,
  "recipientAccountId": "0123456789012",
  "requestID": "d62256aa-fe9b-4fe4-bd7b-8a3917e35d13",
  "requestParameters": {
    "roleArn": "arn:aws:iam::0123456789012:role/ExampleGithubRole",
    "roleSessionName": "botocore-session-1631674835"
  },
  "resources": [
    {
      "ARN": "arn:aws:iam::0123456789012:role/ExampleGithubRole",
      "accountId": "0123456789012",
      "type": "AWS::IAM::Role"
    }
  ],
  "responseElements": {
    "assumedRoleUser": {
      "arn": "arn:aws:sts::0123456789012:assumed-role/ExampleGithubRole/botocore-session-1631674835",
      "assumedRoleId": "AROAY99999AOBPS6VNUFM:botocore-session-1631674835"
    },
    "audience": "https://github.com/aidansteele/aws-federation-github-actions",
    "credentials": {
      "accessKeyId": "ASIAY29999OMG3MKNAG",
      "expiration": "Sep 15, 2021 4:00:36 AM",
      "sessionToken": "IQ[trimmed]lg=="
    },
    "provider": "arn:aws:iam::0123456789012:oidc-provider/vstoken.actions.githubusercontent.com",
    "subjectFromWebIdentityToken": "repo:aidansteele/aws-federation-github-actions:ref:refs/heads/main"
  },
  "sourceIPAddress": "104.211.45.236",
  "tlsDetails": {
    "cipherSuite": "ECDHE-RSA-AES128-GCM-SHA256",
    "clientProvidedHostHeader": "sts.us-east-1.amazonaws.com",
    "tlsVersion": "TLSv1.2"
  },
  "userAgent": "aws-cli/2.2.35 Python/3.8.8 Linux/5.8.0-1040-azure exe/x86_64.ubuntu.20 prompt/off command/sts.get-caller-identity",
  "userIdentity": {
    "identityProvider": "arn:aws:iam::0123456789012:oidc-provider/vstoken.actions.githubusercontent.com",
    "principalId": "arn:aws:iam::0123456789012:oidc-provider/vstoken.actions.githubusercontent.com:https://github.com/aidansteele/aws-federation-github-actions:repo:aidansteele/aws-federation-github-actions:ref:refs/heads/main",
    "type": "WebIdentityUser",
    "userName": "repo:aidansteele/aws-federation-github-actions:ref:refs/heads/main"
  }
}
```

### Can I use those JWT claims as role session tags?

Not directly, unfortunately. AWS requires role session tags to follow a fairly 
specific format - one that I doubt GitHub Actions will implement. ~~But you could
have a token vending machine… stay tuned.~~

**EDIT**: I built an (still cooling down after coming out of the oven) example
of how you could use all those JWT claims as role session tags. Take a look
at [glassechidna/ghaoidc][ghaoidc] and let me know your thoughts.

[roadmap]: https://github.com/github/roadmap/issues/249
[eks]: https://aws.amazon.com/blogs/opensource/introducing-fine-grained-iam-roles-service-accounts/
[ghaoidc]: https://github.com/glassechidna/ghaoidc
