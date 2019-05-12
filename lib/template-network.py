#!/usr/bin/env python
#
# Generates CloudFormation template for VPC - Public
#
import sys
import os
import json
import yaml
import troposphere
import subprocess
from troposphere import Base64, FindInMap, GetAtt, Join, Sub, Output, Export
from troposphere import Parameter, Ref, Tags, Template, Export, Not, Equals
from troposphere.cloudfront import Distribution, DistributionConfig
from troposphere.cloudfront import Origin, DefaultCacheBehavior
from troposphere.ec2 import PortRange, Route, SecurityGroupIngress, RouteTable, SecurityGroup, SubnetRouteTableAssociation
from troposphere.ec2 import VPCGatewayAttachment, Subnet, InternetGateway, Instance, VPC, EIP, EIPAssociation, NatGateway
from troposphere.rds import DBSubnetGroup
from pprint import pprint

sys.path.append(os.path.abspath(os.path.dirname(__file__)) + '/../config')

from config import *


# Currently made for staging env
def get_subnet_names(mode):
    return public_prefixes


def cidr_to_subnets(cidrType):
    public_subnets = {}

    # cidr_map come from config

    vpc_cidr = privateVpcCidr
    cidr_parts = vpc_cidr.split(".")

    for availability_zone in availability_zones:
        items = {}
        for subnet_name in get_subnet_names("public"):
            items[subnet_name] = str(cidr_parts[0]) + "." + str(cidr_parts[1]) + "." + str(cidr_map[availability_zone]["public"][subnet_name]) + ".0/24"

        public_subnets.update({availability_zone: {"public": items}})

    return public_subnets

t = Template()
t.add_description("Network nested stack")

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
        "vpcId",
        Type="String",
        Description="VPC Id"
    ))

t.add_parameter(
    Parameter(
        "igw",
        Type="String",
        Description="Gateway attachment"
    ))


# SUBNETS - All regions
def add_subnets(availability_zones, cidrType, map_public_ip, prefix, postfix):
    subnets = {}
    cidrs = cidr_to_subnets(cidrType)

    for availability_zone in availability_zones:
        subnets[availability_zone] = {}
        subnets[availability_zone][cidrType] = {}

        items = {}
        for subnet_name in get_subnet_names(cidrType):
            items[subnet_name] = t.add_resource(
                Subnet(
                    prefix + availability_zone.replace("-", "") + subnet_name.upper(),
                    VpcId=Ref("vpcId"),
                    AvailabilityZone=availability_zone,
                    CidrBlock=cidrs[availability_zone][cidrType][subnet_name],
                    MapPublicIpOnLaunch=map_public_ip,
                    Tags=Tags(
                        Name=Join("", [Ref("stackName"), "-" + availability_zone + "-" + postfix + "-" + subnet_name.upper()])
                    )
                ))
        subnets[availability_zone][cidrType] = items
    return subnets


public_subnets = add_subnets(availability_zones, "public", "False", "pubsub", "public-subnet")


# ROUTE TABLES - All regions
def add_routing_tables(availability_zones, cidrType, prefix, postfix):
    routing_tables = {}
    for availability_zone in availability_zones:
        routing_tables[availability_zone] = {}
        routing_tables[availability_zone][cidrType] = {}

        items = {}
        for subnet_name in get_subnet_names(cidrType):
            items[subnet_name] = t.add_resource(
                RouteTable(
                    prefix + availability_zone.replace("-", "") + subnet_name.upper(),
                    VpcId=Ref("vpcId"),
                    Tags=Tags(
                        Name=Join("", [Ref("stackName"), "-" + availability_zone + "-" + postfix + "-" + subnet_name]),
                    )
                ))
        routing_tables[availability_zone][cidrType] = items
    return routing_tables


public_routing_tables = add_routing_tables(availability_zones, "public", "pubrttable", "public-route-table")


# ROUTING TABLE ASSOCIATIONS - All regions
def add_public_subnet_assoc(availability_zones, prefix):
    subnet = {}
    for availability_zone in availability_zones:
        subnet[availability_zone] = {}
        subnet[availability_zone]["public"] = {}

        items = {}
        for subnet_name in get_subnet_names("public"):
            items[subnet_name] = t.add_resource(
                SubnetRouteTableAssociation(
                    prefix + availability_zone.replace("-", "") + subnet_name.upper(),
                    RouteTableId=Ref(public_routing_tables[availability_zone]["public"][subnet_name]),
                    SubnetId=Ref(public_subnets[availability_zone]["public"][subnet_name]),
                ))
        subnet[availability_zone]["public"] = items
    return subnet


public_subnet_assoc = add_public_subnet_assoc(availability_zones, "pubsubassoc")

# ROUTES
# Public - All regions
public_routes = {}

for availability_zone in availability_zones:
    public_routes[availability_zone] = {}
    public_routes[availability_zone]["public"] = {}

    # Public internet access
    items = {}
    for subnet_name in get_subnet_names("public"):
        items[subnet_name] = t.add_resource(
            Route(
                "pubrt" + availability_zone.replace("-", "") + subnet_name.upper(),
                GatewayId=Ref("igw"),
                DestinationCidrBlock="0.0.0.0/0",
                RouteTableId=Ref(public_routing_tables[availability_zone]["public"][subnet_name]),
            ))
    public_routes[availability_zone]["public"] = items

"""
Cloudformation
Outputs
"""

# Public Subnets separated - All regions
combined_public = []
combined_public_role = {}

for subnet_name in get_subnet_names("public"):
    combined_public_role[subnet_name] = []
    for availability_zone in availability_zones:
        combined_public.append(Ref(public_subnets[availability_zone]["public"][subnet_name]))
        combined_public_role[subnet_name].append(Ref(public_subnets[availability_zone]["public"][subnet_name]))

for subnet_name in get_subnet_names("public"):
    t.add_output(
        Output(
            stackName + "pubsub" + subnet_name.upper(),
            Description="Public Subnet for referencing " + subnet_name,
            Value=Join(",", combined_public_role[subnet_name]),
            Export=Export(Sub(stackName + "pubsub" + subnet_name.upper())),
        ))

t.add_output(
    Output(
        stackName + "pubsubs",
        Description="Comma separated public subnets.",
        Value=Join(",", combined_public),
        Export=Export(Sub(stackName + "pubsubs")),
    ))

print(t.to_json())
