---
layout: post
title: Apps can now impersonate human access to AWS via IAM Identity Center
date:
  created: 2026-07-01T02:40:00
categories:
  - AWS
  - OIDC
---

Earlier today, AWS IAM Identity Center [launched][launch] the ability for server-side
applications to assume roles on behalf of their users. This is a big deal, I've
wanted this exact kind of functionality for years. The docs are pretty sparse
on how it works and what the events look like in CloudTrail, so here are my
field notes, recommendations on whether you should use it today and feature
requests for whichever AWS service team is working on this.

<!-- more -->

## Background

First, some background on why this is exciting. Let's say that you have a terribly
complicated Terraform setup. Devs struggle to run it on their laptops. So you
want to create an internal hosted service to simplify it. What permissions do
you give this service? You want it to be usable by all of your developers, so
you have to give it at least a superset of all your developers' permissions. 
That's a lot of permissions, but at least now it's functional. And now you have
a new problem: not every developer should be allowed to create/destroy every
resource in every account. So now you need to implement your own AuthZ logic!
This is painful enough at the best of times, but it's especially painful knowing
that the best-case scenario is that you perfectly replicate the developers'
IAM permissions. The worst-case scenario is that you have now effectively given 
them privilege escalation. 

Extrapolate this to every other "helper" use case where a service does something 
in AWS on behalf of a user, and you can see why it would be so immensely useful
if a user could just "pass" their credentials to the service. That's not been
possible, so we resort to locally-executed CLIs and all the pain-points that
entails. The new IAM Identity Center launch (mostly) solves that.

## How it works

It actually works fairly similarly (in principle) to how the AWS CLI works when
you run `aws sso login`, but with an application running in the cloud instead of
on your laptop. Here's a sequence diagram:

```mermaid
sequenceDiagram
    autonumber
    actor Client
    participant IdP
    participant App as App
    participant OIDC as sso-oidc API
    participant IdC as sso API
    participant STS as STS API
    participant CT as CloudTrail

    Client->>IdP: OIDC sign-in (authenticate user)
    IdP-->>Client: signed RS256 JWT

    Client->>App: request + JWT (Authorization: Bearer …)

    App->>OIDC: CreateTokenWithIAM (SigV4)<br/>scope=sso:account:access
    OIDC->>IdP: GET openid-configuration + jwks.json (cached)
    IdP-->>OIDC: JWKS (validate JWT signature)
    OIDC--)CT: CreateTokenWithIAM (full req params)
    OIDC-->>App: access token (credentialId AAAAAGpEaIMI…)

    App->>IdC: ListAccounts (bearer token)
    IdC--)CT: ListAccounts
    IdC-->>App: 14 accounts

    App->>IdC: ListAccountRoles (bearer token)
    IdC--)CT: ListAccountRoles (weird req params)
    IdC-->>App: [AdministratorAccess]
    
    App->>IdC: GetRoleCredentials (bearer token, acct+role)
    IdC->>STS: AssumeRoleWithSAML (SAMLUser, reserved SSO role)
    STS--)CT: AssumeRoleWithSAML
    STS-->>IdC: temp creds ASIA…
    IdC--)CT: GetRoleCredentials (weird req params)
    IdC-->>App: temp AWS credentials (ASIA…)

    App->>STS: GetCallerIdentity (using temp creds)
    STS--)CT: GetCallerIdentity
    STS-->>App: assumed-role/AWSReservedSSO_AdministratorAccess_…/aidan.steele
```

You sign into your IdP (Okta, Entra ID, etc) and get an IdP-issued OIDC token. 
You pass it to your application. Your application exchanges that IdP-issued OIDC 
token for an IdC-issued token. That IdC-issued token can then be used to call 
the various IdC APIs: `ListAccounts` (for accounts you have access to),
`ListAccountRoles` (the roles in those accounts you have access to) and
`GetRoleCredentials` (assuming one of those roles). Note: you don't need to be
signed into IAM Identity Center, only your identity provider.

Now your application can do anything that you can do in AWS, no more and no less.
More on that in "feature requests" below.

## CloudTrail events

Here are the full CloudTrail events. First up is the `sso-oauth:CreateTokenWithIAM` API 
call. This is the only one attributed to the IAM role that the application 
itself runs as. You'll also see I ran my PoC in a Lambda function.

```json
{
  "eventVersion": "1.11",
  "userIdentity": {
    "type": "AssumedRole",
    "principalId": "AROAY24FZKAOBPJTH2BSF:iic-tti-poc-AppFunction-3irLZkLQGPhb",
    "arn": "arn:aws:sts::607481581596:assumed-role/iic-tti-poc-AppFunctionRole-lntyS7rJFEAS/iic-tti-poc-AppFunction-3irLZkLQGPhb",
    "accountId": "607481581596",
    "accessKeyId": "ASIAY24FZKAOLBRPB3V3",
    "sessionContext": {
      "sessionIssuer": {
        "type": "Role",
        "principalId": "AROAY24FZKAOBPJTH2BSF",
        "arn": "arn:aws:iam::607481581596:role/iic-tti-poc-AppFunctionRole-lntyS7rJFEAS",
        "accountId": "607481581596",
        "userName": "iic-tti-poc-AppFunctionRole-lntyS7rJFEAS"
      },
      "attributes": {
        "creationDate": "2026-07-01T00:08:17Z",
        "mfaAuthenticated": "false"
      }
    },
    "inScopeOf": {
      "issuerType": "AWS::Lambda::Function",
      "credentialsIssuedTo": "arn:aws:lambda:ap-southeast-2:607481581596:function:iic-tti-poc-AppFunction-3irLZkLQGPhb",
      "credentialsIssuedToVersion": "arn:aws:lambda:ap-southeast-2:607481581596:function:iic-tti-poc-AppFunction-3irLZkLQGPhb:$LATEST"
    }
  },
  "eventTime": "2026-07-01T00:08:19Z",
  "eventSource": "sso-oauth.amazonaws.com",
  "eventName": "CreateTokenWithIAM",
  "awsRegion": "ap-southeast-2",
  "sourceIPAddress": "54.79.161.228",
  "userAgent": "aws-sdk-go-v2/1.36.3 ua/2.1 os/linux lang/go#1.26.4 md/GOOS#linux md/GOARCH#arm64 api/ssooidc#1.30.1 m/E,g",
  "requestParameters": {
    "clientId": "arn:aws:sso::607481581596:application/ssoins-8259b771d0159cec/apl-82593a19cf4e0ed8",
    "grantType": "urn:ietf:params:oauth:grant-type:jwt-bearer",
    "scope": [
      "sso:account:access"
    ],
    "assertion": "HIDDEN_DUE_TO_SECURITY_REASONS"
  },
  "responseElements": {
    "accessToken": "HIDDEN_DUE_TO_SECURITY_REASONS",
    "expiresIn": 3600,
    "tokenType": "Bearer",
    "issuedTokenType": "urn:ietf:params:oauth:token-type:access_token"
  },
  "additionalEventData": {
    "identitystore:UserId": "976710cc5d-9d976f61-3b89-4b98-88db-2ea3bbc1f3fa",
    "identitystore:IdentityStoreArn": "arn:aws:identitystore::607481581596:identitystore/d-976710cc5d",
    "identitycenter:CredentialId": "AAAAAGpEaIMIfeJrfG3s_yDz-3PQWeDwT9i9d62beJKyBZzks4jkECDTgbezwS8Wx7V8mHW9RyhiUxluexutOs"
  },
  "requestID": "08779d94-3253-400f-9dd4-14f3678f4c46",
  "eventID": "4ad42b1e-b4e0-41f2-b461-6c46021d5120",
  "readOnly": false,
  "resources": [
    {
      "type": "AWS::SSO::Application",
      "ARN": "arn:aws:sso::607481581596:application/ssoins-8259b771d0159cec/apl-82593a19cf4e0ed8"
    }
  ],
  "eventType": "AwsApiCall",
  "managementEvent": true,
  "recipientAccountId": "607481581596",
  "eventCategory": "Management",
  "tlsDetails": {
    "tlsVersion": "TLSv1.3",
    "cipherSuite": "TLS_AES_128_GCM_SHA256",
    "clientProvidedHostHeader": "oidc.ap-southeast-2.amazonaws.com"
  }
}
```

Next is `sso:ListAccounts`. Note that the user identity is now the user, not the
service's role.

```json
{
  "eventVersion": "1.11",
  "userIdentity": {
    "type": "IdentityCenterUser",
    "accountId": "607481581596",
    "onBehalfOf": {
      "userId": "976710cc5d-9d976f61-3b89-4b98-88db-2ea3bbc1f3fa",
      "identityStoreArn": "arn:aws:identitystore::607481581596:identitystore/d-976710cc5d"
    },
    "credentialId": "AAAAAGpEaIMIfeJrfG3s_yDz-3PQWeDwT9i9d62beJKyBZzks4jkECDTgbezwS8Wx7V8mHW9RyhiUxluexutOs"
  },
  "eventTime": "2026-07-01T00:08:19Z",
  "eventSource": "sso.amazonaws.com",
  "eventName": "ListAccounts",
  "awsRegion": "ap-southeast-2",
  "sourceIPAddress": "54.79.161.228",
  "userAgent": "aws-sdk-go-v2/1.36.3 ua/2.1 os/linux lang/go#1.26.4 md/GOOS#linux md/GOARCH#arm64 api/sso#1.25.3 m/E,g",
  "requestParameters": null,
  "responseElements": null,
  "requestID": "389b495a-e5f9-490e-a023-410a4feeeb74",
  "eventID": "b59049be-1afe-4d3e-9abb-9483592a6829",
  "readOnly": true,
  "eventType": "AwsServiceEvent",
  "managementEvent": true,
  "recipientAccountId": "607481581596",
  "eventCategory": "Management"
}
```

Next is `sso:ListAccountRoles`. Note that the account ID doesn't 
appear in `requestParameters`, it is in `serviceEventDetails`.

```json
{
  "eventVersion": "1.11",
  "userIdentity": {
    "type": "IdentityCenterUser",
    "accountId": "607481581596",
    "onBehalfOf": {
      "userId": "976710cc5d-9d976f61-3b89-4b98-88db-2ea3bbc1f3fa",
      "identityStoreArn": "arn:aws:identitystore::607481581596:identitystore/d-976710cc5d"
    },
    "credentialId": "AAAAAGpEaIMIfeJrfG3s_yDz-3PQWeDwT9i9d62beJKyBZzks4jkECDTgbezwS8Wx7V8mHW9RyhiUxluexutOs"
  },
  "eventTime": "2026-07-01T00:08:19Z",
  "eventSource": "sso.amazonaws.com",
  "eventName": "ListAccountRoles",
  "awsRegion": "ap-southeast-2",
  "sourceIPAddress": "54.79.161.228",
  "userAgent": "aws-sdk-go-v2/1.36.3 ua/2.1 os/linux lang/go#1.26.4 md/GOOS#linux md/GOARCH#arm64 api/sso#1.25.3 m/E,g",
  "requestParameters": null,
  "responseElements": null,
  "requestID": "7a88b3b5-547f-48ce-9109-936157d6746e",
  "eventID": "9c48f37a-c7ae-416b-85a0-55ab40ae38df",
  "readOnly": true,
  "eventType": "AwsServiceEvent",
  "managementEvent": true,
  "recipientAccountId": "607481581596",
  "serviceEventDetails": {
    "account_id": "950363612855"
  },
  "eventCategory": "Management"
}
```

Next is `sso:GetRoleCredentials`. Like the previous API event, the role name and
account ID are in `serviceEventDetails`.

```json
{
  "eventVersion": "1.11",
  "userIdentity": {
    "type": "IdentityCenterUser",
    "accountId": "607481581596",
    "onBehalfOf": {
      "userId": "976710cc5d-9d976f61-3b89-4b98-88db-2ea3bbc1f3fa",
      "identityStoreArn": "arn:aws:identitystore::607481581596:identitystore/d-976710cc5d"
    },
    "credentialId": "AAAAAGpEaIMIfeJrfG3s_yDz-3PQWeDwT9i9d62beJKyBZzks4jkECDTgbezwS8Wx7V8mHW9RyhiUxluexutOs"
  },
  "eventTime": "2026-07-01T00:08:20Z",
  "eventSource": "sso.amazonaws.com",
  "eventName": "GetRoleCredentials",
  "awsRegion": "ap-southeast-2",
  "sourceIPAddress": "54.79.161.228",
  "userAgent": "aws-sdk-go-v2/1.36.3 ua/2.1 os/linux lang/go#1.26.4 md/GOOS#linux md/GOARCH#arm64 api/sso#1.25.3 m/E,g",
  "requestParameters": null,
  "responseElements": null,
  "requestID": "8d8e59e3-8e82-4011-afd8-0a804d454b46",
  "eventID": "049a5a98-7ad4-4399-b735-eedddb45aa0f",
  "readOnly": true,
  "eventType": "AwsServiceEvent",
  "managementEvent": true,
  "recipientAccountId": "607481581596",
  "serviceEventDetails": {
    "role_name": "AdministratorAccess",
    "account_id": "950363612855"
  },
  "eventCategory": "Management"
}
```

Next is `sts:AssumeRoleWithSAML`. As best I can tell, there's nothing here (beyond
role name, account ID and timestamps) that can definitively tie this to the 
corresponding `sso:GetRoleCredentials` API call.

```json
{
  "eventVersion": "1.11",
  "userIdentity": {
    "type": "SAMLUser",
    "principalId": "/nQTosBbaHrvuioiTKQkrbl3/WM=:aidan.steele@glassechidna.com.au",
    "userName": "aidan.steele@glassechidna.com.au",
    "identityProvider": "/nQTosBbaHrvuioiTKQkrbl3/WM="
  },
  "eventTime": "2026-07-01T00:08:20Z",
  "eventSource": "sts.amazonaws.com",
  "eventName": "AssumeRoleWithSAML",
  "awsRegion": "ap-southeast-2",
  "sourceIPAddress": "13.239.101.254",
  "userAgent": "aws-sdk-java/2.46.14 md/io#sync md/http#Apache md/internal ua/2.1 api/STS#2.46.x os/Linux#4.14.355-284.735.amzn2.x86_64 lang/java#17.0.19 md/OpenJDK_64-Bit_Server_VM#17.0.19+11-LTS md/vendor#Amazon.com_Inc. md/en_US m/E,N,AJ",
  "requestParameters": {
    "sAMLAssertionID": "_4bed2fda-6aac-47f8-8f04-1cf235869c02",
    "roleSessionName": "aidan.steele@glassechidna.com.au",
    "roleArn": "arn:aws:iam::950363612855:role/aws-reserved/sso.amazonaws.com/ap-southeast-2/AWSReservedSSO_AdministratorAccess_7243976e43c75fc5",
    "principalArn": "arn:aws:iam::950363612855:saml-provider/AWSSSO_9882ccf00912484e_DO_NOT_DELETE",
    "durationSeconds": 43200
  },
  "responseElements": {
    "credentials": {
      "accessKeyId": "ASIA52RQV423TWB3UWEE",
      "sessionToken": "IQoJb[REDACTED FOR BREVITY]fIU=",
      "expiration": "Jul 1, 2026, 12:08:19 PM"
    },
    "assumedRoleUser": {
      "assumedRoleId": "AROA52RQV4237EYPOIPDF:aidan.steele@glassechidna.com.au",
      "arn": "arn:aws:sts::950363612855:assumed-role/AWSReservedSSO_AdministratorAccess_7243976e43c75fc5/aidan.steele@glassechidna.com.au"
    },
    "subject": "aidan.steele@glassechidna.com.au",
    "subjectType": "persistent",
    "issuer": "https://portal.sso.ap-southeast-2.amazonaws.com/saml/assertion/NjA3NDgxNTgxNTk2X2lucy0xZmJjZmIxYzUxMDk3NTZh",
    "audience": "https://signin.aws.amazon.com/saml",
    "nameQualifier": "/nQTosBbaHrvuioiTKQkrbl3/WM="
  },
  "additionalEventData": {
    "ExtendedRequestId": "MTphcC1zb3V0aGVhc3QtMjpTOjE3ODI4NjQ1MDAyNzA6UjpoTW1Nc2ppVw==",
    "RequestDetails": {
      "endpointType": "regional",
      "awsServingRegion": "ap-southeast-2"
    }
  },
  "requestID": "c87269ec-e726-4729-a956-c01e0795b3be",
  "eventID": "423fa918-3e60-4161-812c-8ccb1afbd672",
  "readOnly": true,
  "resources": [
    {
      "accountId": "950363612855",
      "type": "AWS::IAM::Role",
      "ARN": "arn:aws:iam::950363612855:role/aws-reserved/sso.amazonaws.com/ap-southeast-2/AWSReservedSSO_AdministratorAccess_7243976e43c75fc5"
    },
    {
      "accountId": "950363612855",
      "type": "AWS::IAM::SAMLProvider",
      "ARN": "arn:aws:iam::950363612855:saml-provider/AWSSSO_9882ccf00912484e_DO_NOT_DELETE"
    }
  ],
  "eventType": "AwsApiCall",
  "managementEvent": true,
  "recipientAccountId": "950363612855",
  "eventCategory": "Management",
  "tlsDetails": {
    "tlsVersion": "TLSv1.3",
    "cipherSuite": "TLS_AES_128_GCM_SHA256",
    "clientProvidedHostHeader": "sts.ap-southeast-2.amazonaws.com"
  }
}
```

And finally, an API invoked on the user's behalf: `sts:GetCallerIdentity`. 

```json
{
  "eventVersion": "1.11",
  "userIdentity": {
    "type": "AssumedRole",
    "principalId": "AROA52RQV4237EYPOIPDF:aidan.steele@glassechidna.com.au",
    "arn": "arn:aws:sts::950363612855:assumed-role/AWSReservedSSO_AdministratorAccess_7243976e43c75fc5/aidan.steele@glassechidna.com.au",
    "accountId": "950363612855",
    "accessKeyId": "ASIA52RQV4232GGDZ2HL",
    "sessionContext": {
      "sessionIssuer": {
        "type": "Role",
        "principalId": "AROA52RQV4237EYPOIPDF",
        "arn": "arn:aws:iam::950363612855:role/aws-reserved/sso.amazonaws.com/ap-southeast-2/AWSReservedSSO_AdministratorAccess_7243976e43c75fc5",
        "accountId": "950363612855",
        "userName": "AWSReservedSSO_AdministratorAccess_7243976e43c75fc5"
      },
      "attributes": {
        "creationDate": "2026-07-01T00:08:20Z",
        "mfaAuthenticated": "false"
      }
    },
    "onBehalfOf": {
      "userId": "976710cc5d-9d976f61-3b89-4b98-88db-2ea3bbc1f3fa",
      "identityStoreArn": "arn:aws:identitystore::607481581596:identitystore/d-976710cc5d"
    }
  },
  "eventTime": "2026-07-01T00:08:20Z",
  "eventSource": "sts.amazonaws.com",
  "eventName": "GetCallerIdentity",
  "awsRegion": "ap-southeast-2",
  "sourceIPAddress": "54.79.161.228",
  "userAgent": "aws-sdk-go-v2/1.36.3 ua/2.1 os/linux lang/go#1.26.4 md/GOOS#linux md/GOARCH#arm64 api/sts#1.33.19 m/E,e",
  "requestParameters": null,
  "responseElements": null,
  "additionalEventData": {
    "ExtendedRequestId": "MTphcC1zb3V0aGVhc3QtMjpTOjE3ODI4NjQ1MDAzMjg6UjpkYVZ5RjFpag==",
    "RequestDetails": {
      "awsServingRegion": "ap-southeast-2",
      "endpointType": "regional"
    }
  },
  "requestID": "db33a11a-4bf3-442d-a795-459374bba488",
  "eventID": "962b63aa-0b29-444a-89a8-d5d72cd8248b",
  "readOnly": true,
  "eventType": "AwsApiCall",
  "managementEvent": true,
  "recipientAccountId": "950363612855",
  "eventCategory": "Management",
  "tlsDetails": {
    "tlsVersion": "TLSv1.3",
    "cipherSuite": "TLS_AES_128_GCM_SHA256",
    "clientProvidedHostHeader": "sts.ap-southeast-2.amazonaws.com"
  }
}
```

## Feature requests and thoughts

The first request: this is very powerful functionality. Flipping one switch in
IAM Identity Center ("enable AWS account access") grants an application the
ability to impersonate a user and do anything they can do. That's probably too
much power for most applications. As an organisation administrator, I want to 
be able to scope this down. I'd like to be able to say "this application can
only assume roles in these accounts" or "this application can only assume roles
with these names", or even better "this application should use this session 
policy when assuming a user's role".

The second request: if an application is calling AWS APIs on behalf of a user,
I want to know which application is doing so. Imagine an S3 bucket gets deleted
and it's attributed to a user. The user says "I didn't do that", but CloudTrail
shows they clearly did. Right now the innocent user can't prove that it was 
actually an application that deleted the bucket on their behalf. Ideally, the
`userIdentity.onBehalfOf` object could get a new `applicationArn` field that
identifies the application. In the meantime, applications can (and should) 
identify themselves in the `userAgent`.

The third request (similar to the second): there's nothing concretely tying
the `AssumeRoleWithSAML` CloudTrail event to the `GetRoleCredentials` event. 
You can mostly fake it by relying on the tuple of (account ID, role name, 
timestamp) but that's not robust. The `AssumeRoleWithSAML` call doesn't even
include the `userIdentity.onBehalfOf.userId` value (but at least later events
do).

AWS has a reasonably good track record of shipping MVPs that get the basics 
right, and then iterating on them for years and years until they're quite
well-polished services. That is true of IAM Identity Center in general (which
has improved by leaps and bounds recently) and I hope/expect it will remain
true of this particular functionality. I feel like the above requests probably
aren't too unusual, so I wouldn't be surprised if AWS launches them in the coming
weeks or years. 

Should you use it before then? That's hard to say without more context. If you 
trust your code and it unlocks very useful functionality, then maybe it's worth
using today. I'll probably use it for hobby stuff, but I'm unlikely to use it
at my day job until there are more of the requested controls in place. Still
promising, though!

[launch]: https://aws.amazon.com/about-aws/whats-new/2026/06/aws-iam-identity-center-account-access-customer-managed-apps/
