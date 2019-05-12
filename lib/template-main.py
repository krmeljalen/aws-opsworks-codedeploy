#!/usr/bin/env python
#
# Generates CloudFormation template for Main stack
#
import sys
import os
import json
import yaml
import troposphere
from troposphere import Parameter, Ref, Template, GetAtt
from troposphere.cloudformation import Stack
from pprint import pprint

sys.path.append(os.path.abspath(os.path.dirname(__file__)) + '/../config')
from config import *

t = Template()
t.add_version("2010-09-09")

t.add_description("Main stack")

t.add_parameter(
    Parameter(
        "stackName",
        Type="String",
        Description="Stack name",
        Default="MyStack"
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
        AllowedValues=["production", "development"],
        Default="development"
    ))

t.add_parameter(
    Parameter(
        "vpcNetworkGeneralTemplateUrl",
        Type="String",
        Description="S3 url of the General Network template",
        Default="https://s3-" + awsRegion + ".amazonaws.com/" + s3Bucket + "/general.cfn"
    ))

t.add_parameter(
    Parameter(
        "vpcNetworkPublicTemplateUrl",
        Type="String",
        Description="S3 url of the Public Network template",
        Default="https://s3-" +awsRegion + ".amazonaws.com/" + s3Bucket + "/network.cfn"
    ))

t.add_parameter(
    Parameter(
        "vpcInfraTemplateUrl",
        Type="String",
        Description="S3 url of the Infrastructure template",
        Default="https://s3-" + awsRegion + ".amazonaws.com/" + s3Bucket + "/infra.cfn"
    ))

t.add_parameter(
    Parameter(
        "privateVpcCidr",
        Type="String",
        Description="VPC CIDR Mask",
        Default="10.10.0.0/16"
    ))

stack_network_general = t.add_resource(
    Stack(
        "vpcnetworkgeneral",
        TemplateURL=Ref("vpcNetworkGeneralTemplateUrl"),
        Parameters={
            "stackName": Ref("stackName"),
            "vpcCidr": Ref("privateVpcCidr")
        }
    ))

stack_network_public = t.add_resource(
    Stack(
        "vpcnetworkpublic",
        TemplateURL=Ref("vpcNetworkPublicTemplateUrl"),
        Parameters={
            "stackName": Ref("stackName"),
            "vpcId": GetAtt("vpcnetworkgeneral", "Outputs." + stackName + "vpcid"),
            "igw": GetAtt("vpcnetworkgeneral", "Outputs." + stackName + "igw")
        }
    ))

stack_infra = t.add_resource(
    Stack(
        "vpcinfra",
        TemplateURL=Ref("vpcInfraTemplateUrl"),
        Parameters={
            "stackName": Ref("stackName"),
            "keyName": Ref("keyName"),
            "environment": Ref("environment"),
            # This part gets info from Network stack
            "defaultSG": GetAtt("vpcnetworkgeneral", "Outputs." + stackName + "defaultsg"),
            "vpcId": GetAtt("vpcnetworkgeneral", "Outputs." + stackName + "vpcid"),
            "iamCodeDeploy": GetAtt("vpcnetworkgeneral", "Outputs." + stackName + "iamCodeDeploy")
        }
    ))

for prefix in public_prefixes:
    data = t.resources["vpcinfra"].properties["Parameters"].update({"pubsub" + prefix.upper(): GetAtt("vpcnetworkpublic", "Outputs." + stackName + "pubsub" + prefix.upper())})

print(t.to_json())
