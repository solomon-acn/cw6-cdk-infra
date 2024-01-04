from aws_cdk import (
    Stack,
    Fn,
    CfnOutput,
    aws_sagemaker as sagemaker,
    aws_neptune as neptune,
    aws_iam as iam,
    aws_ec2 as ec2,
    aws_s3 as s3,
    aws_dynamodb as dynamodb,
    aws_rekognition as rekognition,
)
from constructs import Construct
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class CwAwsInfraStack(Stack):

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # Retrieve AWS region and account ID
        region = self.region
        account_id = self.account

        #################################################################################################################################
        ### VPC #########################################################################################################################
        #################################################################################################################################

        # Create a VPC with public
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ec2.SubnetType.html
        neptune_vpc = ec2.Vpc(
            self, "CwAwsNeptuneSagemakerEcsVpc",
            max_azs=2,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="PublicSubnet",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="PrivateWithEGRESSSubnet",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24,
                ),
            ],
        )

        # Get the public subnet IDs from the VPC
        public_subnets_ids = neptune_vpc.select_subnets(subnet_group_name="PublicSubnet").subnet_ids

        private_with_egress_subnets_ids = neptune_vpc.select_subnets(subnet_group_name="PrivateWithEGRESSSubnet").subnet_ids

        # Add an S3 VPC endpoint
        neptune_vpc.add_gateway_endpoint(
            "S3Endpoint",
            service=ec2.GatewayVpcEndpointAwsService.S3
        )

        ### Security Group ################################################

        # Create a Neptune security group
        neptune_security_group = ec2.SecurityGroup(
            self, "NeptuneSecurityGroup",
            vpc=neptune_vpc,
            allow_all_outbound=True,  # Allow outbound traffic
        )

        # Create SageMaker security group
        sagemaker_security_group = ec2.SecurityGroup(
            self, "SagemakerSecurityGroup",
            vpc=neptune_vpc,
            allow_all_outbound=True,  # Allow outbound traffic
        )

        # Allow inbound and outbound traffic from the same security group
        
        neptune_security_group.add_ingress_rule(
            peer=neptune_security_group,
            connection=ec2.Port.all_traffic()
        )
        neptune_security_group.add_egress_rule(
            peer=neptune_security_group,
            connection=ec2.Port.all_traffic()
        )

        neptune_security_group.add_ingress_rule(
            peer=sagemaker_security_group,
            connection=ec2.Port.all_traffic()
        )
        neptune_security_group.add_egress_rule(
            peer=sagemaker_security_group,
            connection=ec2.Port.all_traffic()
        )

        # Allow inbound traffic from SageMaker security group to Neptune

        sagemaker_security_group.add_ingress_rule(
            peer=neptune_security_group,
            connection=ec2.Port.all_traffic()
        )
        sagemaker_security_group.add_egress_rule(
            peer=neptune_security_group,
            connection=ec2.Port.all_traffic()
        )

        sagemaker_security_group.add_ingress_rule(
            peer=sagemaker_security_group,
            connection=ec2.Port.all_traffic()
        )
        sagemaker_security_group.add_egress_rule(
            peer=sagemaker_security_group,
            connection=ec2.Port.all_traffic()
        )

        #################################################################################################################################
        ### DynamoDB, S3 & Rekogniton ###################################################################################################
        #################################################################################################################################

        # Create a DynamoDB table
        cw_dynamodb_table_partition_key_name = "id"
        cw_dynamodb_table = dynamodb.Table(
            self, "CwAwsDynamodbTable",
            table_name="cw_dynamodb_table",
            partition_key=dynamodb.Attribute(
                name=cw_dynamodb_table_partition_key_name,
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
        )

        # Output the table name for reference
        CfnOutput(self, "DynamoDBTableName", value=cw_dynamodb_table.table_name, description="DynamoDB Table Name",)
        CfnOutput(self, "DynamoDBTablePartitionKey", value=cw_dynamodb_table_partition_key_name, description="DynamoDB Table partition Key",)

        # Create an S3 bucket
        cw_s3_bucket = s3.Bucket(
            self, "CwAwsS3Bucket",
            bucket_name=f"cw-infra-s3-{account_id}",
            versioned=True,
        )

        # Output the table name for reference
        CfnOutput(self, "S3BucketName", value=cw_s3_bucket.bucket_name, description="S3 Bucket Name",)

        # Create a Rekognition collection
        cw_rekognition_collection = rekognition.CfnCollection(
            self, "CwAwsRekognitionCollection",
            collection_id="cw_rekognition_collection",
        )

        # Output the table name for reference
        CfnOutput(self, "RekognitionollectionId", value=cw_rekognition_collection.collection_id, description="Rekognition Collection Id",)

        # IAM policy for Rekognition
        cw_rekognition_policy = iam.Policy(
            self, "CwAwsRekognitionPolicy",
            statements=[
                iam.PolicyStatement(
                    actions=["rekognition:*"],
                    resources=["*"],
                )
            ],)
        
        # IAM policy for access DynamoDB cw_dynamodb_table
        cw_dynamodb_policy = iam.Policy(
            self, "CwAwsDynamodbPolicy",
            statements=[
                iam.PolicyStatement(
                    actions=["dynamodb:*"],
                    resources=[cw_dynamodb_table.table_arn],
                )
            ],)
        
        # IAM policy for access S3 cw_s3_bucket
        cw_s3_policy = iam.Policy(
            self, "CwAwsS3Policy",
            statements=[
                iam.PolicyStatement(
                    actions=["s3:*"],
                    resources=[cw_s3_bucket.bucket_arn, f"{cw_s3_bucket.bucket_arn}/*"],
                )
            ],)
        
        # Define a Neptune upload to S3 IAM role
        cw_neptune_load_from_s3_role = iam.Role(
            self, 'CwS3ReadOnlyRole',
            assumed_by=iam.ServicePrincipal('rds.amazonaws.com'),
            description='IAM role with S3 read and list access',
            role_name='CwNeptuneloadFromS3AccessRole'  # Set a unique name for your role
        )

        # IAM policy for Read-only access to S3 cw_s3_bucket
        cw_s3_read_only_policy = iam.Policy(
            self, "CwS3ReadOnlyPolicy",
            statements=[
                iam.PolicyStatement(
                    actions=["s3:Get*","s3:List*"],
                    resources=[cw_s3_bucket.bucket_arn, f"{cw_s3_bucket.bucket_arn}/*"],
                )
            ],)

        cw_neptune_load_from_s3_role.attach_inline_policy(cw_s3_read_only_policy)
        CfnOutput(self, "Neptune_S3_upload_IAM_ARN", value=cw_neptune_load_from_s3_role.role_arn, description="ARM for the Neptune upload from S3 role",)
        
        #################################################################################################################################
        ### Neptune instance ############################################################################################################
        #################################################################################################################################

        ## Neptune parameters

        neptune_cfn_dBSubnet_group = neptune.CfnDBSubnetGroup(
            self, "Neptune_CfnDBSubnetGroup",
            db_subnet_group_description="dbSubnetGroupDescription",
            subnet_ids=public_subnets_ids,
            db_subnet_group_name="neptune_dbSubnetGroupName",
        )

        ## Create a Neptune instance within the VPC, associating it with the Neptune security group

        neptune_cluster = neptune.CfnDBCluster(
            self, "CwAwsNeptune",
            db_cluster_identifier="CwAwsNeptune",
            engine_version="1.2.1.0",  # Specify the desired Neptune engine version
            vpc_security_group_ids=[neptune_security_group.security_group_id],
            db_subnet_group_name=neptune_cfn_dBSubnet_group.ref,
            db_port=8182,  # Specify the Neptune cluster port
            associated_roles=[neptune.CfnDBCluster.DBClusterRoleProperty(
                role_arn=cw_neptune_load_from_s3_role.role_arn,
                )]
        )

        neptune_instance = neptune.CfnDBInstance(self, "MyCfnDBInstance",
            db_instance_class="db.t3.medium",
            db_instance_identifier="CwAwsNeptune-db1",
            db_cluster_identifier=neptune_cluster.db_cluster_identifier,
            )
        
        neptune_instance.add_dependency(neptune_cluster)

        # Create an IAM policy simular to IAM policy created by Netptune Workbench
        neptune_sagemaker_setup_policy = iam.Policy(
            self, "CwAwsNeptuneAccessPolicy",
            statements=[
                # to connect to Neptune DB
                iam.PolicyStatement(
                    actions=["neptune-db:*"],
                    resources=[f"arn:aws:rds:{region}:{account_id}:cluster:{neptune_cluster.db_cluster_identifier}/*"],
                ),
                # to get the public resource to set-up the Sagemaker magics
                # https://s3.console.aws.amazon.com/s3/buckets/aws-neptune-notebook
                iam.PolicyStatement(
                    actions=["s3:GetObject","s3:ListBucket"],
                    resources= ["arn:aws:s3:::aws-neptune-notebook","arn:aws:s3:::aws-neptune-notebook/*"],
                ),
                iam.PolicyStatement(
                    actions=["logs:CreateLogGroup","logs:CreateLogStream","logs:PutLogEvents"],
                    resources=["arn:aws:logs:*:*:log-group:/aws/sagemaker/*"],
                ),
            ],
        )

        #################################################################################################################################
        ### SageMakers ##################################################################################################################
        #################################################################################################################################

        # Create an IAM policy for codecommit access for proprietary repository in AWS codecommit
        notebooks_codecommit_policy = iam.Policy(
            self, "CwAwsNotebooksCodecommitAccessPolicy",
            statements=[
                iam.PolicyStatement(
                    actions=["codecommit:GetRepository", "codecommit:GitPull"],
                    resources=[f"{os.environ['PROPRIETARY_REPO_ARN']}"],
                )
            ],
        )

        # Create a SageMaker IAM role 
        sagemaker_iam_role = iam.Role(
            self, "CwAwsSagemakerIAMRole",
            assumed_by=iam.ServicePrincipal("sagemaker.amazonaws.com"),
            role_name="cw-aws-sagemaker-iam-role",
        )

        # Attach policies to the SageMaker IAM role (customize as needed)
        sagemaker_iam_role.attach_inline_policy(neptune_sagemaker_setup_policy)
        sagemaker_iam_role.attach_inline_policy(notebooks_codecommit_policy)
        sagemaker_iam_role.attach_inline_policy(cw_rekognition_policy)
        sagemaker_iam_role.attach_inline_policy(cw_dynamodb_policy)
        sagemaker_iam_role.attach_inline_policy(cw_s3_policy)

        # Neptune on-start stript
        # Do not change indentation, you will regret
        notebook_lifecycle_script = f'''#!/bin/bash
sudo -u ec2-user -i <<'EOF'

echo "export GRAPH_NOTEBOOK_AUTH_MODE=DEFAULT" >> ~/.bashrc
echo "export GRAPH_NOTEBOOK_HOST={neptune_cluster.attr_endpoint}" >> ~/.bashrc
echo "export GRAPH_NOTEBOOK_PORT={neptune_cluster.attr_port}" >> ~/.bashrc
echo "export NEPTUNE_LOAD_FROM_S3_ROLE_ARN=" >> ~/.bashrc
echo "export AWS_REGION={region}" >> ~/.bashrc
aws s3 cp s3://aws-neptune-notebook/graph_notebook.tar.gz /tmp/graph_notebook.tar.gz
rm -rf /tmp/graph_notebook
tar -zxvf /tmp/graph_notebook.tar.gz -C /tmp
/tmp/graph_notebook/install.sh

EOF
'''

        # Neptune Notebook Instance Lifecycle Config
        neptune_notebook_instance_lifecycle_config = sagemaker.CfnNotebookInstanceLifecycleConfig(
            self, "NeptuneNotebookInstanceLifecycleConfig",
            notebook_instance_lifecycle_config_name='aws-neptune-cdk-LC',
            on_start=[sagemaker.CfnNotebookInstanceLifecycleConfig.NotebookInstanceLifecycleHookProperty(
                content=Fn.base64(notebook_lifecycle_script))
                ]
        )

        # Neptune Notebook Instance
        neptune_notebook_instance = sagemaker.CfnNotebookInstance(
            self,"CwAwsSagemaker",
            notebook_instance_name="cw-aws-sagemaker",
            instance_type="ml.t3.medium",
            subnet_id=public_subnets_ids[0],
            security_group_ids=[sagemaker_security_group.security_group_id],
            role_arn=sagemaker_iam_role.role_arn,
            lifecycle_config_name=neptune_notebook_instance_lifecycle_config.notebook_instance_lifecycle_config_name,
            default_code_repository=f"{os.environ['PROPRIETARY_REPO']}"
        )