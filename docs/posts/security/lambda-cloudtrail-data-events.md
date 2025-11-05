---
layout: post
title: Lambda CloudTrail data events
date:
  created: 2023-03-21T06:03:00
categories:
  - AWS
---

<!-- more -->

Today I was experimenting with CloudTrail data events for Lambda invocations,
because I learned that [as of 2021][eni-blog], these data events log the ENI ID
used by a Lambda function invocation. For completeness, the event looks like this:

```json
{
  "eventVersion": "1.08",
  "userIdentity": {
    "invokedBy": "states.amazonaws.com",
    "type": "AssumedRole",
    "principalId": "AROAEXAMPLEZGVVXB2VC:wozynIhxRGfTvfRlXhHKONdyrIaAmRyN",
    "arn": "arn:aws:sts::012345679012:assumed-role/My-RoleName-1746R4C1N6UFS/wozynIhxRGfTvfRlXhHKONdyrIaAmRyN",
    "accountId": "012345679012",
    "accessKeyId": "ASIAEXAMPLEQMIZPFY5",
    "sessionContext": {
      "sessionIssuer": {
        "type": "Role",
        "principalId": "AROAEXAMPLEZGVVXB2VC",
        "arn": "arn:aws:iam::012345679012:role/My-RoleName-1746R4C1N6UFS",
        "accountId": "012345679012",
        "userName": "My-RoleName-1746R4C1N6UFS"
      },
      "attributes": {
        "creationDate": "2023-03-21T05:32:03Z",
        "mfaAuthenticated": "false"
      }
    }
  },
  "eventTime": "2023-03-21T05:32:03Z",
  "eventSource": "lambda.amazonaws.com",
  "eventName": "Invoke",
  "awsRegion": "us-east-1",
  "sourceIPAddress": "states.amazonaws.com",
  "userAgent": "states.amazonaws.com",
  "requestParameters": null,
  "responseElements": null,
  "additionalEventData": {
    "customerEniId": "eni-02258670f86ec5c51",
    "functionVersion": "arn:aws:lambda:us-east-1:012345679012:function:my-function-name:23"
  },
  "requestID": "006ee61e-4b61-4de5-b3b8-99b4d72ca7e7",
  "eventID": "b1e55492-d8be-4b9a-b794-a8a0a28162f0",
  "readOnly": false,
  "resources": [
    {
      "accountId": "012345679012",
      "type": "AWS::Lambda::Function",
      "ARN": "arn:aws:lambda:us-east-1:012345679012:function:my-function-name"
    }
  ],
  "eventType": "AwsApiCall",
  "managementEvent": false,
  "recipientAccountId": "012345679012",
  "eventCategory": "Data"
}
```

The ENI ID is at `$.additionalEventData.customerEniId`. It's also worth noting that
the executed function _version_ is logged, but not the alias used for the `lambda.Invoke()`
API call.

## Bonus

A pair of CloudTrail events caught my eye. There was a record with `"eventName": "InvokeExecution"`.
I tried googling for "InvokeExecution" and got very few results. I figured fellow
CloudTrail nerds might have mentioned it, so I tried searching the Cloud Security 
Forum slack and found this:

![prior question](/assets/2023-03-21-slack-question.png)

...turns out that I had asked the exact same question almost exactly a year ago
and had forgotten all about it. So I thought I'd blog about it solely so Google
indexes this and I can find it next time I forget about this and look it up again.

For the record: `InvokeExecution` events happen when a Lambda function is invoked
asynchronously, i.e. with an `InvocationType: "Event"` parameter. They appear in
pairs (or more, if the invocation fails and is retried): there is an `Invoke`
event and one or more `InvokeExecution` events. They can be correlated by the
CloudTrail record's `requestID` attribute - which also matches the request ID
in the function's CloudWatch Logs output. Interestingly, the `Invoke` record
_does_ include the invoked alias (unlike the synchronous execution in the previous
example). The executed version and ENI ID are in the `InvokeExecution` record.
Here are examples:

### Invoke

```json
{
  "eventVersion": "1.08",
  "userIdentity": {
    "type": "AWSService",
    "invokedBy": "events.amazonaws.com"
  },
  "eventTime": "2023-03-21T05:32:03Z",
  "eventSource": "lambda.amazonaws.com",
  "eventName": "Invoke",
  "awsRegion": "us-east-1",
  "sourceIPAddress": "events.amazonaws.com",
  "userAgent": "events.amazonaws.com",
  "requestParameters": {
    "functionName": "arn:aws:lambda:us-east-1:012345679012:function:my-function-name:live",
    "invocationType": "Event",
    "sourceArn": "arn:aws:events:us-east-1:012345679012:rule/my-rule-name-VMA1FQWKHEIL",
    "sourceAccount": "012345679012"
  },
  "responseElements": null,
  "additionalEventData": {
    "functionVersion": "arn:aws:lambda:us-east-1:012345679012:function:my-function-name:14"
  },
  "requestID": "6baa1b22-d95f-4550-8528-2d0e0ea5b845",
  "eventID": "32321ee4-ffd9-4fae-9207-a9bb12efc18c",
  "readOnly": false,
  "resources": [
    {
      "accountId": "012345679012",
      "type": "AWS::Lambda::Function",
      "ARN": "arn:aws:lambda:us-east-1:012345679012:function:my-function-name"
    }
  ],
  "eventType": "AwsApiCall",
  "managementEvent": false,
  "recipientAccountId": "012345679012",
  "sharedEventID": "675fc334-334b-47a2-b2e0-f831cc51196c",
  "eventCategory": "Data"
}
```

### InvokeExecution

```json
{
  "eventVersion": "1.08",
  "userIdentity": {
    "type": "AWSService",
    "invokedBy": "lambda.amazonaws.com"
  },
  "eventTime": "2023-03-21T05:32:04Z",
  "eventSource": "lambda.amazonaws.com",
  "eventName": "InvokeExecution",
  "awsRegion": "us-east-1",
  "sourceIPAddress": "lambda.amazonaws.com",
  "userAgent": "lambda.amazonaws.com",
  "requestParameters": null,
  "responseElements": null,
  "additionalEventData": {
    "customerEniId": "eni-0fe91c93d7934f8a0",
    "functionVersion": "arn:aws:lambda:us-east-1:012345679012:function:my-function-name:14"
  },
  "requestID": "6baa1b22-d95f-4550-8528-2d0e0ea5b845",
  "eventID": "904d57aa-6ff8-43e0-9a78-a4ad67c32595",
  "readOnly": false,
  "resources": [
    {
      "accountId": "012345679012",
      "type": "AWS::Lambda::Function",
      "ARN": "arn:aws:lambda:us-east-1:012345679012:function:my-function-name"
    }
  ],
  "eventType": "AwsApiCall",
  "managementEvent": false,
  "recipientAccountId": "012345679012",
  "sharedEventID": "f7d6a59b-1dbe-4114-94db-a8f10ed0a000",
  "eventCategory": "Data"
}
```

[eni-blog]: https://aws.amazon.com/about-aws/whats-new/2021/12/aws-lambda-hyperplane-eni-cloudtrail-events/
