
# Welcome to your CDK Python project!

This is a blank project for CDK development with Python.

The `cdk.json` file tells the CDK Toolkit how to execute your app.

This project is set up like a standard Python project.  The initialization
process also creates a virtualenv within this project, stored under the `.venv`
directory.  To create the virtualenv it assumes that there is a `python3`
(or `python` for Windows) executable in your path with access to the `venv`
package. If for any reason the automatic creation of the virtualenv fails,
you can create the virtualenv manually.


# Before install the packages, it is recommended to set-up PyEnv and Poetry to manage the pythong environment
https://dev.to/mattcale/pyenv-poetry-bffs-20k6

To manually create a virtualenv on MacOS and Linux with poery:
reference to https://stackoverflow.com/questions/72796618/can-you-manage-a-cdk-project-with-poetry

```
$ poetry init
```

After the init poetry to create pyproject.toml, you need to copy the package requirement list in requirement.txt to the pyproject.toml.
you can use the following step to activate and install the package listed in pyproject.toml 

```
$ poetry install
```

Before running the next step, you need to make sure the IAM user / role have enought permission, it is recommended to attach below policys
- AmazonSSMFullAccess
- AWSCloudFormationFullAccess

At this point you can now synthesize the CloudFormation template for this code.

```
$ cdk synth
```

The next step you need to run will be cdk bootstrapping, but you will need to add the minimal permission to create aws resource for CDK / CloudFormation deployment
https://docs.aws.amazon.com/cdk/v2/guide/bootstrapping.html
https://github.com/aws/aws-cdk/issues/21937
The minimal policy JSON is inside the folder manual_aws_setup for reference: cdk_bootstrap_least_privilege_permission.json 
```
$ cdk bootstrapping
``` 

After bootstrapping and set-up the IAM role, S3 bucket and CDKToolkit in CloudFormation, we are almost ready for the next deploy.
we need to add the assume role policy to the IAM user / user group, so that it can use the IAM role created by cdk bootstrappiing to deploy CloudFormation stack
https://stackoverflow.com/questions/34922920/how-can-i-allow-a-group-to-assume-a-role
https://stackoverflow.com/questions/68275460/default-credentials-can-not-be-used-to-assume-new-style-deployment-roles
The example policy JSON is insdie the folder manual_aws_setup for reference: cdk_deploy_assume_role_policy.json
```
$ cdk deploy
```

To tear down the stack, run
```
$ cdk destroy
```

To add additional dependencies, for example other CDK libraries, just add
them to your `setup.py` file and rerun the `pip install -r requirements.txt`
command.

## Useful commands

 * `cdk ls`          list all stacks in the app
 * `cdk synth`       emits the synthesized CloudFormation template
 * `cdk deploy`      deploy this stack to your default AWS account/region
 * `cdk diff`        compare deployed stack with current state
 * `cdk docs`        open CDK documentation

Enjoy!
