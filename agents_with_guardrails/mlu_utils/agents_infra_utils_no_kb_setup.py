import logging
import boto3
import random
import time
import zipfile
from io import BytesIO
import json
import uuid
import pprint
import os
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth

### NOTE: change the logging level to DEBUG if infrasetup fails to get more trace on the issue
logging.basicConfig(format='[%(asctime)s] p%(process)s {%(filename)s:%(lineno)d} %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

prefix_infra = None
prefix_iam = None
suffix = None

sts_client = boto3.client('sts')
iam_client = boto3.client('iam')
s3_client = boto3.client('s3')
lambda_client = boto3.client('lambda')

session = boto3.session.Session()
region = session.region_name
account_id = sts_client.get_caller_identity()["Account"]
region, account_id
# getting boto3 clients for required AWS services

from botocore.config import Config 

timeout_config = Config(read_timeout=1800)

bedrock_agent_client = boto3.client('bedrock-agent')
bedrock_agent_runtime_client = boto3.client('bedrock-agent-runtime', config=timeout_config)
open_search_serverless_client = boto3.client('opensearchserverless')

# getting boto3 clients for required AWS services
sts_client = boto3.client('sts')
iam_client = boto3.client('iam')
s3_client = boto3.client('s3')
lambda_client = boto3.client('lambda')


def generate_prefix_for_agent_infra():
    random_uuid = str(uuid.uuid4())
    prefix_infra = 'l2' + random_uuid[0:6]
    prefix_iam = 'l2'+ random_uuid.split('-')[1]
    
    logger.info(f"random_uuid :: {random_uuid} prefix_infra :: {prefix_infra} prefix_iam :: {prefix_iam}")
    return prefix_infra, prefix_iam


def setup_agent_infrastructure(schema_filename, kb_db_file_uri, lambda_code_uri):
    
    # prefix and suffix names
    prefix_infra, prefix_iam = generate_prefix_for_agent_infra()
    suffix = f"{account_id}" #{region}-

    agent_name = f"{prefix_infra}-agent-kb"
    agent_alias_name = f"{prefix_infra}-workshop-alias"
    bucket_name = f'{agent_name}-{suffix}'
    bucket_arn = f"arn:aws:s3:::{bucket_name}"
    schema_key = f'{agent_name}-schema.json' # file in repo
    schema_name = schema_filename
    schema_arn = f'arn:aws:s3:::{bucket_name}/{schema_key}'
    bedrock_agent_bedrock_allow_policy_name = 'SageMakerNotebookPolicy' #f"{prefix_iam}-bedrock-allow-{suffix}"
    bedrock_agent_s3_allow_policy_name = 'RetailBotAgentRoleDefaultPolicy' #f"{prefix_iam}-s3-allow-{suffix}"
    bedrock_agent_kb_allow_policy_name = f"{prefix_iam}-kb-allow-{suffix}"
    lambda_role_name = 'AmazonBedrockLambdaExecutionRoleForAgentsRetailbot02' #f'{agent_name}-lambda-role-{suffix}'
    agent_role_name = 'AmazonBedrockExecutionRoleForAgentsRetailbot02'        #f'AmazonBedrockExecutionRoleForAgents_{prefix_iam}'
    lambda_code_path = lambda_code_uri # file in repo
    lambda_name = f'LambdaAgentsRetailbot02'

    ## KB with DB
    kb_db_tag = 'kbdb'

    kb_db_name = f'{prefix_infra}-{kb_db_tag}-{suffix}'
    kb_db_data_source_name = f'{prefix_infra}-{kb_db_tag}-docs-{suffix}'
    kb_db_files_path = kb_db_file_uri # file path keep as-is
    kb_db_key = f'{kb_db_tag}_{prefix_infra}'
    kb_db_role_name = f'AmazonBedrockExecutionRoleForKnowledgeBase_{prefix_infra}_{kb_db_tag}_icakb'
    kb_db_bedrock_allow_policy_name = f"ica-{kb_db_tag}-{prefix_infra}-bedrock-allow-{suffix}"
    kb_db_aoss_allow_policy_name = f"ica-{kb_db_tag}-{prefix_infra}-aoss-allow-{suffix}"
    kb_db_s3_allow_policy_name = f"ica-{kb_db_tag}-{prefix_infra}-s3-allow-{suffix}"
    kb_db_collection_name = f'{prefix_iam}-{kb_db_tag}-{suffix}' 
    # Select Amazon titan as the embedding model
    kb_db_embedding_model_arn = f'arn:aws:bedrock:{region}::foundation-model/amazon.titan-embed-text-v1'
    kb_db_vector_index_name = f"bedrock-knowledge-base-{prefix_infra}-{kb_db_tag}-index"
    kb_db_metadataField = f'bedrock-knowledge-base-{prefix_infra}-{kb_db_tag}-metadata'
    kb_db_textField = f'bedrock-knowledge-base-{prefix_infra}-{kb_db_tag}-text'
    kb_db_vectorField = f'bedrock-knowledge-base-{prefix_infra}-{kb_db_tag}-vector'



    # ## Knowledge Base 1 : DB

    # ### Create S3 bucket and upload API Schema and Knowledge Base files
    # 
    # Agents require an API Schema stored on s3. Let's create an S3 bucket to store the file and upload the necessary files to the newly created bucket

    

    # Create S3 bucket for Open API schema
    logger.info(f"region :: {region} ")
    s3bucket = None
    if region.lower() == "us-east-1":
        s3bucket = s3_client.create_bucket(
            Bucket=bucket_name
        )
    else:
        s3bucket = s3_client.create_bucket(
            Bucket=bucket_name,
            CreateBucketConfiguration={'LocationConstraint': region}
        )
    s3bucket = s3_client.create_bucket(
        Bucket=bucket_name,
        CreateBucketConfiguration={'LocationConstraint': region}
    )


    # Upload Open API schema to this s3 bucket
    s3_client.upload_file(schema_name, bucket_name, schema_key)

    
    
    # Upload Knowledge Base files to this s3 bucket
    # the DDL script is required for the LLM to learn how to write queries
    print(f"kb_db_files_path :: {kb_db_files_path} kb_db_key :: {kb_db_key}")
    for f in os.listdir(kb_db_files_path):
        if f.endswith(".sql") or f.endswith("db"):
            s3_client.upload_file(kb_db_files_path+'/'+f, bucket_name, f)

    lambda_iam_role = iam_client.get_role(
            RoleName=lambda_role_name
    )
    agent_role = iam_client.get_role(
        RoleName=agent_role_name
    )
    
    agent_bedrock_policy = None
    agent_s3_schema_policy = None
        
    for policy in iam_client.list_policies()['Policies']:
        #print(policy)
        if bedrock_agent_bedrock_allow_policy_name in policy['PolicyName']:
            agent_bedrock_policy = policy['Arn']
        
        if bedrock_agent_s3_allow_policy_name in policy['PolicyName']:
            agent_s3_schema_policy = policy['Arn']

    print(f"agent_bedrock_policy :: {agent_bedrock_policy}")
    print(f"agent_s3_schema_policy :: {agent_s3_schema_policy}")
    '''
    print(f"Create IAM Role for the Lambda function")
    # Create IAM Role for the Lambda function
    try:
        assume_role_policy_document = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": "bedrock:InvokeModel",
                    "Principal": {
                        "Service": "lambda.amazonaws.com"
                    },
                    "Action": "sts:AssumeRole"
                }
            ]
        }

        assume_role_policy_document_json = json.dumps(assume_role_policy_document)

        lambda_iam_role = iam_client.create_role(
            RoleName=lambda_role_name,
            AssumeRolePolicyDocument=assume_role_policy_document_json
        )
        #print(f"Create IAM lambda_iam_role for the Lambda function : {lambda_iam_role}")
        # Pause to make sure role is created
        time.sleep(20)
    except Exception as inst:
        print(f"exception = {inst}")
        lambda_iam_role = iam_client.get_role(RoleName=lambda_role_name)

    iam_client.attach_role_policy(
        RoleName=lambda_role_name,
        PolicyArn='arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole'
    )
    iam_client.attach_role_policy(
        RoleName=lambda_role_name,
        PolicyArn='arn:aws:iam::aws:policy/AmazonS3FullAccess'
    )
    '''

    # Package up the lambda function code
    s = BytesIO()
    z = zipfile.ZipFile(s, 'w')
    z.write(lambda_code_path)
    z.close()
    zip_content = s.getvalue()

    # Delete Lambda function if exists
    for lambdas in lambda_client.list_functions()['Functions']:
        if lambda_name in lambdas['FunctionName']:
            lambda_client.delete_function(
                FunctionName=lambda_name
            )
    
    # Create Lambda Function
    lambda_function = lambda_client.create_function(
        FunctionName=lambda_name,
        Runtime='python3.12',
        Timeout=900,
        Role=lambda_iam_role['Role']['Arn'],
        Code={'ZipFile': zip_content},
        Handler='lambda_retail_agent.lambda_handler',
        Environment={
            'Variables': {
                'BUCKET_NAME': bucket_name,
                'KB_PREFIX': kb_db_key
            }
        },
    )

    '''
    We will now create our agent. To do so, we first need to create the agent policies that allow bedrock model invocation and s3 bucket access.
    # amazon.titan-text-premier-v1:0 and anthropic.claude-3-haiku-20240307-v1:0
    '''

    '''
    bedrock_agent_bedrock_allow_policy_statement = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "AmazonBedrockAgentBedrockFoundationModelPolicy",
                "Effect": "Allow",
                "Action": "bedrock:InvokeModel",
                "Resource": [
                    f"arn:aws:bedrock:{region}::foundation-model/anthropic.claude-3-haiku-20240307-v1:0"
                ]
            },
            {  
                "Sid": "AmazonBedrockAgentBedrockApplyGuardrailPolicy",
                "Effect": "Allow",
                "Action": "bedrock:ApplyGuardrail",
                "Resource": [ 
                    f"arn:aws:bedrock:{region}:{account_id}:guardrail/an9l3icjg3kj"
                ]
            }
        ]
    }

    bedrock_policy_json = json.dumps(bedrock_agent_bedrock_allow_policy_statement)

    agent_bedrock_policy = iam_client.create_policy(
        PolicyName=bedrock_agent_bedrock_allow_policy_name,
        PolicyDocument=bedrock_policy_json
    )


    bedrock_agent_s3_allow_policy_statement = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "AllowAgentAccessOpenAPISchema",
                "Effect": "Allow",
                "Action": ["s3:GetObject"],
                "Resource": [
                    schema_arn
                ]
            }
        ]
    }


    bedrock_agent_s3_json = json.dumps(bedrock_agent_s3_allow_policy_statement)
    agent_s3_schema_policy = iam_client.create_policy(
        PolicyName=bedrock_agent_s3_allow_policy_name,
        Description=f"Policy to allow invoke Lambda that was provisioned for it.",
        PolicyDocument=bedrock_agent_s3_json
    )

    # Create IAM Role for the agent and attach IAM policies
    assume_role_policy_document = {
        "Version": "2012-10-17",
        "Statement": [{
              "Effect": "Allow",
              "Principal": {
                "Service": "bedrock.amazonaws.com"
              },
              "Action": "sts:AssumeRole"
        }
        ]
    }
    

    assume_role_policy_document_json = json.dumps(assume_role_policy_document)
    agent_role = iam_client.create_role(
        RoleName=agent_role_name,
        AssumeRolePolicyDocument=assume_role_policy_document_json
    )
    
    logger.debug(f"agent_name :: {agent_name}  >>>>>  agent_role :: {agent_role}")

    # Pause to make sure role is created
    time.sleep(10)

    iam_client.attach_role_policy(
        RoleName=agent_role_name,
        PolicyArn=agent_bedrock_policy['Policy']['Arn']
    )

    iam_client.attach_role_policy(
        RoleName=agent_role_name,
        PolicyArn=agent_s3_schema_policy['Policy']['Arn']
    )

    '''

    logger.info(f"bucket_name :: {bucket_name} \n agent_name :: {agent_name} \n agent_alias_name :: {agent_alias_name} \n schema_key :: {schema_key}  ")

    infra_response = {
        "agent_name": agent_name,
        "agent_alias_name": agent_alias_name,
        "agent_role": agent_role,
        "bucket_name": bucket_name,
        "schema_key": schema_key,
        "lambda_name": lambda_name,
        "lambda_function": lambda_function,
        "agent_bedrock_policy": agent_bedrock_policy,
        "agent_s3_schema_policy": agent_s3_schema_policy,
        "agent_role_name": agent_role_name,
        "lambda_role_name": lambda_role_name
    }
    return infra_response



def cleanup_infrastructure(agent_action_group_response, lambda_name, lambda_function, lambda_role_name, agent_id, agent_alias_id, agent_role_name, bucket_name, schema_key, agent_bedrock_policy, agent_s3_schema_policy):

    # 
    # The next steps are optional and demonstrate how to delete our agent. To delete the agent we need to:
    # 1. update the action group to disable it
    # 2. delete agent action group
    # 3. delete agent alias
    # 4. delete agent
    # 5. delete lambda function
    # 6. empty created s3 bucket
    # 7. delete s3 bucket


    # This is not needed, you can delete agent successfully after deleting alias only
    # Additionaly, you need to disable it first

    if agent_action_group_response is not None:
        action_group_id = agent_action_group_response['agentActionGroup']['actionGroupId']
        action_group_name = agent_action_group_response['agentActionGroup']['actionGroupName']

    response = bedrock_agent_client.update_agent_action_group(
        agentId=agent_id,
        agentVersion='DRAFT',
        actionGroupId= action_group_id,
        actionGroupName=action_group_name,
        actionGroupExecutor={
            'lambda': lambda_function['FunctionArn']
        },
        apiSchema={
            's3': {
                's3BucketName': bucket_name,
                's3ObjectKey': schema_key
            }
        },
        actionGroupState='DISABLED',
    )

    action_group_deletion = bedrock_agent_client.delete_agent_action_group(
        agentId=agent_id,
        agentVersion='DRAFT',
        actionGroupId= action_group_id
    )


    agent_alias_deletion = bedrock_agent_client.delete_agent_alias(
        agentId=agent_id,
        agentAliasId=agent_alias_id
    )

    agent_deletion = bedrock_agent_client.delete_agent(
    agentId=agent_id
    )

    
    # Delete Lambda function
    lambda_client.delete_function(
        FunctionName=lambda_name
    )
    
    # Empty and delete S3 Bucket

    objects = s3_client.list_objects(Bucket=bucket_name)  
    if 'Contents' in objects:
        for obj in objects['Contents']:
            s3_client.delete_object(Bucket=bucket_name, Key=obj['Key']) 
    s3_client.delete_bucket(Bucket=bucket_name)

    # Delete IAM Roles and policies

    if agent_bedrock_policy is not None and agent_s3_schema_policy is not None:
        for policy in [
            agent_bedrock_policy, 
            agent_s3_schema_policy
        ]:
            response = iam_client.list_entities_for_policy(
                PolicyArn=policy['Policy']['Arn'],
                EntityFilter='Role'
            )

            for role in response['PolicyRoles']:
                iam_client.detach_role_policy(
                    RoleName=role['RoleName'], 
                    PolicyArn=policy['Policy']['Arn']
                )

            iam_client.delete_policy(
                PolicyArn=policy['Policy']['Arn']
            )

        iam_client.detach_role_policy(RoleName=lambda_role_name, PolicyArn='arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole')
        iam_client.detach_role_policy(RoleName=lambda_role_name, PolicyArn='arn:aws:iam::aws:policy/AmazonS3FullAccess')


        for role_name in [
            agent_role_name, 
            lambda_role_name
        ]:
            try: 
                iam_client.delete_role(
                    RoleName=role_name
                )
            except Exception as e:
                print(e)
                print("couldn't delete role", role_name)

    print(f"Cleanup completed >>>>>> ")
