#!/bin/bash
if [ ! -f /home/ec2-user/first ]
then
    aws s3 cp s3://stackcodebucket/userdata.sh /home/ec2-user/userdata.sh
    chmod +x /home/ec2-user/userdata.sh
    bash /home/ec2-user/userdata.sh
    # Prevent puppet from updating code on its own
    sed -i 's/\[main\]/\[main\]\nruninterval = 5y/g' /etc/puppetlabs/puppet/puppet.conf
    service puppet restart
    touch /home/ec2-user/first
fi
