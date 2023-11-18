from aws_cdk import App, Stack, Tags
from constructs import Construct
from aws_cdk import aws_sagemaker as sagemaker
from aws_cdk import aws_neptune as neptune
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_ecs_patterns as ecs_patterns
from aws_cdk import aws_iam as iam
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_secretsmanager as secretsmanager
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_dynamodb as dynamodb

class CwAwsInfraStack(Stack):

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # Retrieve AWS region and account ID
        region = self.region
        account_id = self.account

        ### VPC ####################################################

        # Create a VPC with public and private subnets
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ec2.SubnetType.html
        vpc = ec2.Vpc(
            self, "CwAwsNeptuneSagemakerEcsVpc",
            max_azs=2,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="PublicSubnet",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="PrivateSubnet",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=24,
                ),
            ],
        )

        # Get the public subnet IDs from the VPC
        public_subnets_ids = vpc.select_subnets(subnet_group_name="PublicSubnet").subnet_ids

        # Get the private subnet IDs from the VPC
        private_subnets_ids = vpc.select_subnets(subnet_group_name="PrivateSubnet").subnet_ids
        
        # Add tags to the stack
        Tags.of(self).add("StackType", "CwAwsInfraStack")

        ### Security Group ################################################

        # Create a Neptune security group
        neptune_security_group = ec2.SecurityGroup(
            self, "NeptuneSecurityGroup",
            vpc=vpc,
            allow_all_outbound=True,  # Allow outbound traffic
        )

        # Create SageMaker security group
        sagemaker_security_group = ec2.SecurityGroup(
            self, "SagemakerSecurityGroup",
            vpc=vpc,
            allow_all_outbound=True,  # Allow outbound traffic
        )

        # Allow inbound traffic from SageMaker security group to Neptune
        neptune_security_group.add_ingress_rule(
            sagemaker_security_group,
            ec2.Port.tcp(8182),  # Adjust the port as needed
        )

        ### Neptune instance ######################################################

        neptune_cfn_dBSubnet_group = neptune.CfnDBSubnetGroup(
            self, "Neptune_CfnDBSubnetGroup",
            db_subnet_group_description="dbSubnetGroupDescription",
            subnet_ids=private_subnets_ids,

            # the properties below are optional
            db_subnet_group_name="neptune_dbSubnetGroupName",
        )

        # Create a Neptune instance within the VPC, associating it with the Neptune security group
        neptune_cluster = neptune.CfnDBCluster(
            self, "CwAwsNeptune",
            db_cluster_identifier="CwAwsNeptune",
            engine_version="1.2.1.0",  # Specify the desired Neptune engine version
            vpc_security_group_ids=[neptune_security_group.security_group_id],
            db_subnet_group_name=neptune_cfn_dBSubnet_group.ref ,      # .ref is suggested by chatGPT, and it say it is a common practice; I cannot find any source supporting it, but it work ....
            db_port=8182,  # Specify the Neptune cluster port
        )

        # Add tags to the Neptune cluster
        Tags.of(neptune_cluster).add("cloudwar", "true")

        # Create an IAM policy for Neptune access
        neptune_access_policy = iam.Policy(
            self, "NeptuneAccessPolicy",
            statements=[
                iam.PolicyStatement(
                    actions=["neptune-db:Connect"],
                    resources=[f"arn:aws:rds:{region}:{account_id}:cluster/{neptune_cluster.db_cluster_identifier}"],
                )
            ],
        )

        ### ECS cluster ######################################################

        # Create an Amazon ECS cluster
        ecs_cluster = ecs.Cluster(
            self, "CwAwsEcsCluster",
            vpc=vpc,
            container_insights=True,  # Enable CloudWatch Container Insights
        )

        # Add the default Cloud Map namespace
        ecs_cluster.add_default_cloud_map_namespace(
            name="cloudwar.local",
        )

        # Attach the Neptune access policy to the ECS task role
        ecs_task_role = iam.Role(
            self, "ECSTaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        )
        ecs_task_role.attach_inline_policy(neptune_access_policy)

        # Add tags to the Fargate cluster
        Tags.of(ecs_cluster).add("cloudwar", "true")

        ### ECS task ######################################################

        # Create a simple "Hello World" Fargate task
        hello_world_task = ecs.FargateTaskDefinition(
            self, "HelloWorldTask",
        )

        hello_world_container = hello_world_task.add_container(
            "HelloWorldContainer",
            image=ecs.ContainerImage.from_registry("amazon/amazon-ecs-sample"),
            # Replace with the actual image of your "Hello World" application
        )

        # Define the port mapping for the container
        hello_world_container.add_port_mappings(ecs.PortMapping(
            container_port=80,  # The port your application listens on
            host_port=80,       # The port on the host (usually the same as container port for HTTP)
        ))

        # # Commented out because when update stack, the update runs forever
        # # Create an ECS Fargate service with an Application Load Balancer
        # ecs_patterns.ApplicationLoadBalancedFargateService(
        #     self, "HelloWorldService",
        #     cluster=ecs_cluster,        # Required
        #     cpu=256,                    # Default is 256
        #     desired_count=1,            # Default is 1
        #     task_definition=hello_world_task,
        #     memory_limit_mib=512,      # Default is 512
        #     public_load_balancer=True)  # Set this to false if you want a private load balancer

        ### SageMakers ######################################################

        # Create a SageMaker IAM role with permissions to use Neptune
        sagemaker_iam_role = iam.Role(
            self, "CwAwsSagemakerIAMRole",
            assumed_by=iam.ServicePrincipal("sagemaker.amazonaws.com"),
            role_name="cw-aws-sagemaker-iam-role",
        )

        # Attach policies to the SageMaker IAM role (customize as needed)
        sagemaker_iam_role.attach_inline_policy(neptune_access_policy)

        # Create an IAM policy for Neptune access
        notebooks_codecommit_policy = iam.Policy(
            self, "cw_notebook_codecommit_access_policy",
            statements=[
                iam.PolicyStatement(
                    actions=["codecommit:GetRepository", "codecommit:GitPull"],
                    resources=["arn:aws:codecommit:eu-west-2:026391457579:cw_sagemaker_notebooks"],
                )
            ],
        )

        # Attach policies to the SageMaker IAM role (customize as needed)
        sagemaker_iam_role.attach_inline_policy(notebooks_codecommit_policy)

        # Create a SageMaker notebook instance
        sagemaker_notebook = sagemaker.CfnNotebookInstance(
            self, "CwAwsSagemaker",
            instance_type="ml.t2.medium",
            role_arn=sagemaker_iam_role.role_arn,
            notebook_instance_name="cw-aws-sagemaker",
            default_code_repository="https://git-codecommit.eu-west-2.amazonaws.com/v1/repos/cw_sagemaker_notebooks", # Manually created in the same region - London
            security_group_ids=[sagemaker_security_group.security_group_id],
            subnet_id=public_subnets_ids[0],
        )

        ## S3 Bucket and DynamoDB #######################################

        # Create a S3 bucket
        bucket = s3.Bucket(self, "cw_cdk_testbucket", versioned=True)

        # Create a DynamoDB table
        cw_face_index_table = dynamodb.Table(
            self, "CwFaceIndexTable",
            table_name="CwFaceIndexTable",
            partition_key=dynamodb.Attribute(
                name="FaceId",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,  # You can adjust this as needed
        )

        


# Create the CDK app and stack
app = App()
CwAwsInfraStack(app, "CwAwsInfraStack")
app.synth()
