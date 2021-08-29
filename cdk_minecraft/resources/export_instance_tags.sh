# fetch instance info
INSTANCE_ID=$(curl -s http://169.254.169.254/latest/meta-data/instance-id)
REGION=$(curl -s http://169.254.169.254/latest/meta-data/placement/region)


# export instance tags
# export_statement=$(aws ec2 describe-tags --region "$REGION" \
#                         --filters "Name=resource-id,Values=$INSTANCE_ID" \
#                         --query 'Tags[?!contains(Key, `:`)].[Key,Value]' \
#                         --output text | \
#                         sed -E 's/^([^\s\t]+)[\s\t]+([^\n]+)$/export \1="\2"/g')

# eval $export_statement

# export instance info
export MINECRAFT_HOME="/opt/minecraft"
export INSTANCE_ID
export REGION