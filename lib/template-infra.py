#!/usr/bin/env python
#
# Generates CloudFormation template for VPC - Infrastructure
#
import sys
import os
import json
import yaml
import troposphere
import subprocess
from troposphere import Base64, FindInMap, GetAtt, Join, Sub, Output, Export
from troposphere import Parameter, Ref, Tags, Template, Export, Not, Equals, Split
from troposphere.ec2 import SecurityGroup, SecurityGroupIngress, BlockDeviceMapping, EBSBlockDevice
from troposphere.autoscaling import LaunchConfiguration, AutoScalingGroup, Tag
from troposphere.elasticloadbalancing import LoadBalancer, ConnectionDrainingPolicy, HealthCheck, Listener
from troposphere.elasticloadbalancingv2 import ListenerRule, Action, Condition, TargetGroup, Matcher, TargetGroupAttribute
from troposphere.elasticloadbalancingv2 import Listener as ListenerALB
from troposphere.elasticloadbalancingv2 import LoadBalancer as LoadBalancerALB
from troposphere.elasticloadbalancingv2 import Certificate as CertificateALB
from troposphere.elasticache import CacheCluster
from troposphere.elasticache import SecurityGroup as CacheSecurityGroup
from troposphere.elasticache import SecurityGroupIngress as CacheSecurityGroupIngress
from troposphere.efs import FileSystem, MountTarget
from pprint import pprint

sys.path.append(os.path.abspath(os.path.dirname(__file__)) + '/../config')

from config import *

t = Template()
t.add_description("Infrastructure nested stack")
t.add_version("2010-09-09")

"""
Cloudformation
Parameters
"""

# Additional useful parameters

t.add_parameter(
    Parameter(
        "stackName",
        Type="String",
        Description="Stack name",
    ))

t.add_parameter(
    Parameter(
        "keyName",
        Type="String",
        Description="SSH Keypair name"
    ))

t.add_parameter(
    Parameter(
        "environment",
        Type="String",
        Description="Environment stack is running in (production,development)",
        AllowedValues=["production", "development"]
    ))

t.add_parameter(
    Parameter(
        "iamCodeDeploy",
        Type="String",
        Description="Iam role for codedeploy"
    ))

for prefix in public_prefixes:
    t.add_parameter(
        Parameter(
            "pubsub" + prefix.upper(),
            Type="String",
            Description="Public subnets for " + prefix.upper()
        ))

# Parameters from network stack

t.add_parameter(
    Parameter(
        "defaultSG",
        Type="String",
        Description="default VPC Security Group"
    ))

t.add_parameter(
    Parameter(
        "vpcId",
        Type="String",
        Description="VPC Id for referencing"
    ))

"""
Cloudformation
Resources
"""

serverSecurityGroup = t.add_resource(SecurityGroup(
    "ServerSecurityGroup",
    VpcId=Ref("vpcId"),
    GroupName="ServerSecurityGroup",
    GroupDescription="default Server Security group.",
    SecurityGroupIngress=[{
        "IpProtocol": "-1",
        "CidrIp": '0.0.0.0/0'  # Allows all traffic for debug purposes
    }],
    Tags=Tags(
        Environment=Ref("environment")
    )
))

# All traffic between instances allowed.
serverSecurityGroupIngress = t.add_resource(SecurityGroupIngress(
    "ServerSecurityGroupIngress",
    IpProtocol="-1",
    GroupId=Ref("ServerSecurityGroup"),
    SourceSecurityGroupId=Ref("ServerSecurityGroup")
))

elbSecurityGroup = t.add_resource(SecurityGroup(
    "ElbSecurityGroup",
    VpcId=Ref("vpcId"),
    GroupName="ElbSecurityGroup",
    GroupDescription="default ELB Security group.",
    SecurityGroupIngress=[{
        "IpProtocol": "tcp",
        "FromPort": 80,
        "ToPort": 80,
        "CidrIp": '0.0.0.0/0'
    }, {
        "IpProtocol": "tcp",
        "FromPort": 443,
        "ToPort": 443,
        "CidrIp": '0.0.0.0/0'
    }
    ],
    Tags=Tags(
        Environment=Ref("environment")
    )
))

#
# Microservices start here
#

# roles and roleconfig come from config
for role in roles:
    # Dont name this resource since named resources need full stack destroy.
    launchConfig = t.add_resource(LaunchConfiguration(
        "launchconfig" + role.upper(),
        ImageId=rolemap[role]["instance"]["ami"],
        SecurityGroups=[Ref("defaultSG"), Ref(serverSecurityGroup)],
        InstanceType=rolemap[role]["instance"]["type"],
        IamInstanceProfile=Ref("iamCodeDeploy"),
        AssociatePublicIpAddress=True,
        KeyName=Ref("keyName"),
        BlockDeviceMappings=[BlockDeviceMapping(DeviceName="/dev/xvda", Ebs=EBSBlockDevice(DeleteOnTermination=True, VolumeType="gp2", VolumeSize=10))],
        UserData=Base64(Join('', [
            '#!/bin/bash\n',
            'sudo apt-get install wget\n',
            'wget https://aws-codedeploy-',
            awsRegion,
            '.s3.amazonaws.com/latest/install\n',
            'chmod +x ./install\n',
            'sudo ./install auto\n',
        ]))
    ))

    loadbalancer = []
    targetgroup = []

    if "elb" in rolemap[role]:
        elb_identifier = ""
        if rolemap[role]["elb"]["subnet"] in public_prefixes:
            elb_identifier = "pubsub" + rolemap[role]["elb"]["subnet"].upper()

        elb = t.add_resource(LoadBalancer(
            "elb" + role.upper(),
            Subnets=Split(",", Ref(elb_identifier)),
            Listeners=[
                Listener(
                    LoadBalancerPort=80,
                    InstancePort=80,
                    Protocol='HTTP',
                ),
            ],
            SecurityGroups=[Ref("defaultSG"), Ref(elbSecurityGroup)],
            HealthCheck=HealthCheck(
                Target=rolemap[role]["elb"]["healthcheck"],
                HealthyThreshold="2",
                UnhealthyThreshold="2",
                Interval="10",
                Timeout="5"
            ),
            ConnectionDrainingPolicy=ConnectionDrainingPolicy(
                Enabled=True,
                Timeout=300
            ),
            CrossZone=True,
            Tags=Tags(
                Environment=Ref("environment"),
                Service=role
            )
        ))

        loadbalancer = [Ref(elb)]

    identifier = ""
    if rolemap[role]["instance"]["subnet"] in public_prefixes:
        identifier = "pubsub" + rolemap[role]["instance"]["subnet"].upper()

    # Dont name this resource since named resources need full stack destroy.
    t.add_resource(AutoScalingGroup(
        "autoscaling" + role.upper(),
        VPCZoneIdentifier=Split(",", Ref(identifier)),
        LaunchConfigurationName=Ref(launchConfig),
        LoadBalancerNames=loadbalancer,
        TargetGroupARNs=targetgroup,
        MinSize=rolemap[role]["autoscaling"]["min"],
        MaxSize=rolemap[role]["autoscaling"]["max"],
        Tags=[
            Tag("Environment", Ref("environment"), "true"),
            Tag("Name", Join("-", [Ref("stackName"), role]), "true"),
            Tag("Service", role, "true"),
            Tag("Role", role, "true"),
            Tag("pp_role", rolemap[role]["instance"]["pp_role"], "true")
        ]
    ))


print(t.to_json())
