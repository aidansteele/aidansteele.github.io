---
layout: post
title: Cheap serverless containers using API Gateway
date:
  created: 2022-10-15T23:47:52
categories:
  - AWS
---

<!-- more -->

Sometimes I need to run a long-lived app. In those cases I reach for AWS ECS
Fargate instead of AWS Lambda. You can run a container on Fargate for as little 
as $9/month, or $2.70/month if you're happy to roll the dice with Fargate Spot
(I usually do!)

If you have a web app, you almost certainly use a load balancer in front of your
containers. And this is where the cost goes from "fun side project" to "oh, I'm
not sure I'm willing to spend _that_ much money on this." The load balancer by 
itself is at least $16.40/month - you could run six containers for that price!

## No need for load balancers

You can forego the ALB entirely - and still get TLS termination and balancing
load over multiple containers. You just need to use API Gateway HTTP API's
[support for private integrations][private-integrations]. These allow you to
specify the origin behind the API Gateway as a HTTP endpoint inside a VPC, rather
than the typical Lambda function ARN.

**Instead of $16.40+/month you pay only $1 per million requests**. For the traffic
volumes that my hobby projects receive, that's a huge saving. 

## Deployable example

Here's a complete deployable example. There are two templates.

The first template is the base infrastructure. You would deploy this once into
your account, and it can be shared across the many web apps you will deploy
at example.com. It contains:

* A VPC and its associated subnets, route tables, etc.
* A Route 53 hosted zone for your DNS records
* An ACM-managed TLS certificate (used by API Gateway later)
* An API Gateway VPC Link and its security group. This is how API GW "reaches in"
  to the container running in your VPC.
* A [Cloud Map][cloudmap] namespace. 

The second template contains everything specific to a single application hosted
on example.com. You would deploy multiple stacks from this template, one for each
serverless app you have developed. It contains:

* An ECS task definition
* IAM roles for your ECS task definition
* A CloudMap service. This holds the IP addresses of your running containers
* An ECS service. This runs one copy of your task and registers/deregisters
  Fargate IPs with the CloudMap service when tasks start and stop.
* A security group for your ECS service that only allows the VPC link to make
  requests to it.
* An API gateway that forwards all requests to the CloudMap service via the
  VPC link.
* An API Gateway API mapping and Route 53 record to make your API accessible
  at my-app.example.com.

Note that the ECS task definition contains a health check. This is because API
Gateway itself doesn't perform health checks like an ALB would - it's up to
you to tell ECS how it should check the health of your container. Here I have
chosen to have ECS run `curl` inside the container.

```yaml
# vpc-infra.yml
Resources:
  HostedZone:
    Type: AWS::Route53::HostedZone
    Properties:
      Name: example.com

  Certificate:
    Type: AWS::CertificateManager::Certificate
    Properties:
      DomainName: example.com
      ValidationMethod: DNS
      SubjectAlternativeNames:
        - "*.example.com"
      DomainValidationOptions:
        - DomainName: example.com
          HostedZoneId: !Ref HostedZone

  CloudMapNamespace:
    Type: AWS::ServiceDiscovery::PrivateDnsNamespace
    Properties:
      Vpc: !Ref Vpc
      Name: example

  VpcLink:
    Type: AWS::ApiGatewayV2::VpcLink
    Properties:
      Name: vpclink
      SecurityGroupIds:
        - !Ref VpcLinkSecurityGroup
      SubnetIds:
        - !Ref SubnetA
        - !Ref SubnetB

  VpcLinkSecurityGroup:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupDescription: vpc link
      VpcId: !Ref VpcId
      SecurityGroupIngress: []
      
  Vpc:
    Type: AWS::EC2::VPC
    Properties:
      EnableDnsHostnames: true
      EnableDnsSupport: true
      CidrBlock: 10.1.0.0/16

  SubnetA:
    Type: AWS::EC2::Subnet
    Properties:
      VpcId: !Ref Vpc
      CidrBlock: 10.1.1.0/24
      AvailabilityZone: !Sub ${AWS::Region}a

  SubnetB:
    Type: AWS::EC2::Subnet
    Properties:
      VpcId: !Ref Vpc
      CidrBlock: 10.1.2.0/24
      AvailabilityZone: !Sub ${AWS::Region}b

  InternetGateway:
    Type: AWS::EC2::InternetGateway

  GatewayAttachment:
    Type: AWS::EC2::VPCGatewayAttachment
    Properties:
      VpcId: !Ref Vpc
      InternetGatewayId: !Ref InternetGateway

  RouteTable:
    Type: AWS::EC2::RouteTable
    Properties:
      VpcId: !Ref Vpc

  InternetRoute:
    Type: AWS::EC2::Route
    DependsOn: GatewayAttachment
    Properties:
      GatewayId: !Ref InternetGateway
      RouteTableId: !Ref RouteTable
      DestinationCidrBlock: 0.0.0.0/0

  RouteTableAssociationSubnetA:
    Type: AWS::EC2::SubnetRouteTableAssociation
    Properties:
      SubnetId: !Ref SubnetA
      RouteTableId: !Ref RouteTable

  RouteTableAssociationSubnetB:
    Type: AWS::EC2::SubnetRouteTableAssociation
    Properties:
      SubnetId: !Ref SubnetB
      RouteTableId: !Ref RouteTable

Outputs:
  HostedZone:
    Value: !Ref HostedZone
    Export:
      Name: HostedZoneId
  Certificate:
    Value: !Ref Certificate
    Export:
      Name: Certificate
  CloudMapNamespace:
    Value: !Ref CloudMapNamespace
    Export:
      Name: CloudMapNamespace      
  VpcLink:
    Value: !Ref VpcLink
    Export:
      Name: VpcLink
  VpcLinkSecurityGroup:
    Value: !Ref VpcLinkSecurityGroup
    Export:
      Name: VpcLinkSecurityGroup
  Vpc:
    Value: !Ref Vpc
    Export:
      Name: VpcId
  SubnetA:
    Value: !Ref SubnetA
    Export:
      Name: SubnetA
  SubnetB:
    Value: !Ref SubnetB
    Export:
      Name: SubnetB  
```

```yaml
# cheap-container-app.yml
Parameters:
  Image:
    Type: String
    Default: nginx
    
Resources:
  Service:
    Type: AWS::ECS::Service
    Properties:
      ServiceName: my-app
      TaskDefinition: !Ref TaskDefinition
      DesiredCount: 1
      ServiceRegistries:
        - RegistryArn: !GetAtt CloudMapService.Arn
          Port: 80
      NetworkConfiguration:
        AwsvpcConfiguration:
          AssignPublicIp: ENABLED
          Subnets:
            - !ImportValue SubnetA
            - !ImportValue SubnetB
          SecurityGroups:
            - !Ref FargateSecurityGroup

  FargateSecurityGroup:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupDescription: my app
      VpcId: !ImportValue VpcId
      SecurityGroupIngress:
        - SourceSecurityGroupId: !ImportValue VpcLinkSecurityGroup
          FromPort: 80
          ToPort: 80
          IpProtocol: tcp

  TaskDefinition:
    Type: AWS::ECS::TaskDefinition
    Properties:
      Family: my-app
      Volumes: []
      Cpu: 256
      Memory: 512
      NetworkMode: awsvpc
      TaskRoleArn: !Ref TaskRole
      ExecutionRoleArn: !Ref ExecutionRole
      ContainerDefinitions:
        - Name: main
          Image: !Ref Image
          HealthCheck:
            Command:
              - CMD-SHELL
              - curl --fail http://127.0.0.1
          PortMappings:
            - ContainerPort: 80
              Protocol: tcp

  CloudMapService:
    Type: AWS::ServiceDiscovery::Service
    Properties:
      NamespaceId: !ImportValue CloudMapNamespace
      Name: my-app.example
      DnsConfig:
        DnsRecords:
          - Type: SRV
            TTL: 60
      HealthCheckCustomConfig:
        FailureThreshold: 1

  TaskRole:
    Type: AWS::IAM::Role
    Properties:
      AssumeRolePolicyDocument:
        Statement:
          - Effect: Allow
            Principal:
              Service: [ecs-tasks.amazonaws.com]
            Action: sts:AssumeRole

  ExecutionRole:
    Type: AWS::IAM::Role
    Properties:
      AssumeRolePolicyDocument:
        Statement:
          - Effect: Allow
            Action: sts:AssumeRole
            Principal:
              Service: [ecs-tasks.amazonaws.com]
      ManagedPolicyArns:
        - arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy

  ApiGateway:
    Type: AWS::ApiGatewayV2::Api
    Properties:
      ProtocolType: HTTP
      Name: my-app

  Integration:
    Type: AWS::ApiGatewayV2::Integration
    Properties:
      ApiId: !Ref ApiGateway
      ConnectionId: !ImportValue VpcLink
      ConnectionType: VPC_LINK
      IntegrationMethod: ANY
      IntegrationType: HTTP_PROXY
      IntegrationUri: !GetAtt CloudMapService.Arn
      PayloadFormatVersion: 1.0

  Stage:
    Type: AWS::ApiGatewayV2::Stage
    Properties:
      ApiId: !Ref ApiGateway
      StageName: $default
      AutoDeploy: true

  Route:
    Type: AWS::ApiGatewayV2::Route
    Properties:
      ApiId: !Ref ApiGateway
      RouteKey: $default
      Target: !Sub integrations/${Integration}

  GatewayDomain:
    Type: AWS::ApiGatewayV2::DomainName
    Properties:
      DomainName: my-app.example.com
      DomainNameConfigurations:
        - EndpointType: REGIONAL
          CertificateArn: !ImportValue Certificate

  GatewayMapping:
    Type: AWS::ApiGatewayV2::ApiMapping
    Properties:
      ApiId: !Ref ApiGateway
      DomainName: !Ref GatewayDomain
      Stage: !Ref Stage

  Record:
    Type: AWS::Route53::RecordSet
    Properties:
      HostedZoneId: !ImportValue HostedZoneId
      Name: my-app.example.com
      Type: A
      AliasTarget:
        DNSName: !GetAtt GatewayDomain.RegionalDomainName
        HostedZoneId: !GetAtt GatewayDomain.RegionalHostedZoneId
```

## Thoughts

After writing out those templates, I get the feeling that this could be the kind
of thing that would be a useful AWS CDK module, for the CDK-inclined. If anyone
wants to build it, I'd be happy to update this post with a link to it.

[private-integrations]: https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-develop-integrations-private.html
[cloudmap]: https://aws.amazon.com/cloud-map/
