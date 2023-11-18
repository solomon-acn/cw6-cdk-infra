import aws_cdk as core
import aws_cdk.assertions as assertions

from cw_aws_infra.cw_aws_infra_stack import CwAwsInfraStack

# example tests. To run these tests, uncomment this file along with the example
# resource in cw_aws_infra/cw_aws_infra_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = CwAwsInfraStack(app, "cw-aws-infra")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
