#!/usr/bin/env python
#
# Generates CloudFormation template for VPC
#
import sys
import os
import json
import yaml
import troposphere
import subprocess
from troposphere import Base64, FindInMap, GetAtt, Join, Sub, Output, Export
from troposphere import Parameter, Ref, Tags, Template, Export, Not, Equals
from troposphere.iam import Role, Policy, InstanceProfile
from troposphere.ec2 import VPCGatewayAttachment, InternetGateway, VPC
from troposphere.codedeploy import (
    Application,
    AutoRollbackConfiguration,
    DeploymentGroup,
    DeploymentStyle,
    Ec2TagFilters,
    Ec2TagSet,
    Ec2TagSetListObject,
    ElbInfoList,
    LoadBalancerInfo,
    OnPremisesInstanceTagFilters,
)

sys.path.append(os.path.abspath(os.path.dirname(__file__)) + '/../config')
from config import *

from pprint import pprint

t = Template()
t.add_description("Network general stack")


"""
Cloudformation
Parameters
"""
t.add_parameter(
    Parameter(
        "stackName",
        Type="String",
        Description="Stack name",
    ))

t.add_parameter(
    Parameter(
        "vpcCidr",
        Type="String",
        Description="VPC Cidr Block",
        Default="10.10.0.0/16",
    ))


"""
Cloudformation
Resources
"""
vpc = t.add_resource(
    VPC(
        "vpc",
        EnableDnsSupport="true",
        CidrBlock=Ref("vpcCidr"),
        EnableDnsHostnames="true",
        Tags=Tags(
            Name=Join("", [Ref("stackName"), "-vpc"]),
        )
    ))

internet_gateway = t.add_resource(
    InternetGateway(
        "igw",
        Tags=Tags(
            Name=Join("", [Ref("stackName"), "-internet-gateway"]),
        )
    ))

t.add_resource(
    VPCGatewayAttachment(
        "attachgw",
        VpcId=Ref(vpc),
        InternetGatewayId=Ref(internet_gateway),
    ))

#
# Code Deploy stuff
#

codedeploy_service_role = t.add_resource(Role(
    stackName + "CodeDeployServiceIAMRole",
    AssumeRolePolicyDocument={
        "Version": "2012-10-17",
        "Statement": [{
            "Sid": "CodeDeployTrustPolicy",
            "Effect": "Allow",
            "Principal": {
                "Service": ["codedeploy.amazonaws.com"]
            },
            "Action": "sts:AssumeRole"
        }]
    },
    Path="/",
    ManagedPolicyArns=["arn:aws:iam::aws:policy/service-role/AWSCodeDeployRole"]
))

code_deploy_instance_role = t.add_resource(Role(
    stackName + "CodeDeployInstanceIAMRole",
    RoleName=stackName + "CodeDeployInstanceIAMRole",
    Policies=[Policy(
        PolicyName=stackName + "CodeDeployInstanceIAMRole",
        PolicyDocument={
        "Version": "2012-10-17",
        "Statement": [
            {
            "Effect": "Allow",
            "Action": [
                "s3:Get*",
                "s3:List*"
            ],
            "Resource": [
                "arn:aws:s3:::" + s3CodeBucket,
                "arn:aws:s3:::" + s3CodeBucket + "/*",
                "arn:aws:s3:::aws-codedeploy-us-east-2/*",
                "arn:aws:s3:::aws-codedeploy-us-east-1/*",
                "arn:aws:s3:::aws-codedeploy-us-west-1/*",
                "arn:aws:s3:::aws-codedeploy-us-west-2/*",
                "arn:aws:s3:::aws-codedeploy-ca-central-1/*",
                "arn:aws:s3:::aws-codedeploy-eu-west-1/*",
                "arn:aws:s3:::aws-codedeploy-eu-west-2/*",
                "arn:aws:s3:::aws-codedeploy-eu-west-3/*",
                "arn:aws:s3:::aws-codedeploy-eu-central-1/*",
                "arn:aws:s3:::aws-codedeploy-ap-northeast-1/*",
                "arn:aws:s3:::aws-codedeploy-ap-northeast-2/*",
                "arn:aws:s3:::aws-codedeploy-ap-southeast-1/*",
                "arn:aws:s3:::aws-codedeploy-ap-southeast-2/*",
                "arn:aws:s3:::aws-codedeploy-ap-south-1/*",
                "arn:aws:s3:::aws-codedeploy-sa-east-1/*"
            ]
            }, {
                "Action": [
                    "opsworks-cm:AssociateNode",
                    "opsworks-cm:DescribeNodeAssociationStatus",
                    "opsworks-cm:DescribeServers",
                    "ec2:DescribeTags"
                ],
                "Resource": "*",
                "Effect": "Allow"
            }
        ]
        }
    )],
    AssumeRolePolicyDocument={
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "",
                "Effect": "Allow",
                "Principal": {
                    "Service": "ec2.amazonaws.com"
                },
                "Action": "sts:AssumeRole"
            }
        ]
    }
))

codedeploy_instance_profile = t.add_resource(InstanceProfile(
    stackName + "CodeDeployInstanceProfile",
    Roles=[Ref(code_deploy_instance_role)]
))

application = t.add_resource(Application(
    stackName,
    ApplicationName=stackName,
    ComputePlatform="Server"
))

deployment_groups = {}

for role in roles:
    deployment_groups[role] = DeploymentGroup(
        stackName + role + "DeploymentGroup",
        DeploymentGroupName=role.capitalize(),
        ApplicationName=stackName,
        DependsOn=application,
        AutoRollbackConfiguration=AutoRollbackConfiguration(
            Enabled=True,
            Events=['DEPLOYMENT_FAILURE']
        ),
        DeploymentStyle=DeploymentStyle(
            DeploymentOption='WITHOUT_TRAFFIC_CONTROL'
        ),
        ServiceRoleArn=GetAtt(stackName + "CodeDeployServiceIAMRole", "Arn"),
        Ec2TagSet=Ec2TagSet(
            Ec2TagSetList=[
                Ec2TagSetListObject(
                    Ec2TagGroup=[
                        Ec2TagFilters(
                            Key="Role",
                            Type="KEY_AND_VALUE",
                            Value=role
                        ),
                    ]
                )
            ]
        )
    )
    t.add_resource(deployment_groups[role])

"""
Cloudformation
Outputs
"""
t.add_output(
    Output(
        stackName + "vpcid",
        Description="VPC ID of a stack.",
        Value=Ref(vpc),
        Export=Export(Sub(stackName + "vpcid")),
    ))

t.add_output(
    Output(
        stackName + "vpccidr",
        Description="VPC Cidr mask.",
        Value=Ref("vpcCidr"),
        Export=Export(Sub(stackName + "vpccidr")),
    ))

t.add_output(
    Output(
        stackName + "defaultsg",
        Description="Default Security group id.",
        Value=GetAtt("vpc", "DefaultSecurityGroup"),
        Export=Export(stackName + "defaultsg"),
    ))

t.add_output(
    Output(
        stackName + "igw",
        Description="VPC GW ID of a stack.",
        Value=Ref(internet_gateway),
        Export=Export(Sub(stackName + "igw")),
    ))

t.add_output(
    Output(
        stackName + "iamCodeDeploy",
        Value=Ref(codedeploy_instance_profile)
    ))

print(t.to_json())
