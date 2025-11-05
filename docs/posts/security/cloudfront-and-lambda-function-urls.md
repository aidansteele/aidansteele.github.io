---
layout: post
title: CloudFront and Lambda function URLs
date:
  created: 2022-10-16T23:08:52
categories:
  - AWS
---

<!-- more -->

In April 2022, AWS Lambda [announced the launch of function URLs][aws-blog] - a
way to invoke websites powered by Lambda functions without needing API Gateway.
A common complaint was the lack of support for custom domains: it only supported
the URLs it would generate that look like `lprqaxgvt4f6ab3dbj3ixftr640uzgie.lambda-url.ap-southeast-2.on.aws`.

But that's where CloudFront comes in useful. Not only can it provide us with 
custom domain functionality, but we get caching, WAF support, etc as well.
Here's a template I've been using for my apps:

```yaml
Transform: AWS::Serverless-2016-10-31

Parameters:
  CertificateArn:
    Type: String
  HostedZoneId:
    Type: String
  Domain:
    Type: String

Resources:
  Function:
    Type: AWS::Serverless::Function
    Properties:
      CodeUri: ./webapp
      AutoPublishAlias: live
      MemorySize: 1024
      Timeout: 30
      Architectures: [arm64]
      Runtime: provided.al2
      Handler: unused
      FunctionUrlConfig:
        AuthType: AWS_IAM

  CloudFront:
    Type: AWS::CloudFront::Distribution
    Properties:
      DistributionConfig:
        Enabled: true
        HttpVersion: http2and3
        Aliases:
          - !Ref Domain
        ViewerCertificate:
          AcmCertificateArn: !Ref CertificateArn
          MinimumProtocolVersion: TLSv1.2_2021
          SslSupportMethod: sni-only
        DefaultCacheBehavior:
          ViewerProtocolPolicy: redirect-to-https
          Compress: true
          CachePolicyId: 658327ea-f89d-4fab-a63d-7e88639e58f6 # Managed-CachingOptimized
          OriginRequestPolicyId: 59781a5b-3903-41f3-afcb-af62929ccde1 # Managed-CORS-CustomOrigin
          TargetOriginId: web
        Origins:
          - Id: web
            DomainName: !Select [2, !Split ["/", !GetAtt FunctionUrl.FunctionUrl]]
            OriginAccessControlId: !Ref OAC
            CustomOriginConfig:
              OriginProtocolPolicy: https-only
              OriginSSLProtocols: [TLSv1.2]
            OriginShield:
              Enabled: true
              OriginShieldRegion: !Ref AWS::Region

  Permission:
    Type: AWS::Lambda::Permission
    Properties:
      Action: lambda:InvokeFunctionUrl
      FunctionName: !Ref Function.Alias
      FunctionUrlAuthType: AWS_IAM
      Principal: cloudfront.amazonaws.com
      SourceArn: !Sub arn:aws:cloudfront::${AWS::AccountId}:distribution/${CloudFront}

  OAC:
    Type: AWS::CloudFront::OriginAccessControl
    Properties:
      OriginAccessControlConfig:
        Name: !Ref AWS::StackName
        OriginAccessControlOriginType: lambda
        SigningBehavior: always
        SigningProtocol: sigv4

  Record:
    Type: AWS::Route53::RecordSet
    Properties:
      HostedZoneId: !Ref HostedZoneId
      Name: !Ref Domain
      Type: A
      AliasTarget:
        DNSName: !GetAtt CloudFront.DomainName
        HostedZoneId: Z2FDTNDATAQYW2 # this is documented as the cloudfront hosted zone id
```

**Update 24/07/2024**: CloudFront added support for AWS IAM authentication when
connecting to Lambda function URLs. I have updated the template to use that. This
means that even if an attacker discovers your Lambda function URL, they can't
bypass CloudFront - this is useful if you rely on WAF protections.

[aws-blog]: https://aws.amazon.com/blogs/aws/announcing-aws-lambda-function-urls-built-in-https-endpoints-for-single-function-microservices/
