---
layout: post
title: Lambda extension environment variables
date:
  created: 2022-12-15T22:35:52
categories:
  - AWS
---

<!-- more -->

This is really just some context for myself so I don't have to write code to
sanity-check myself each time. Here are the environment variables available to
an AWS Lambda **extension** in the `provided.al2` runtime:

| Name                            | Value                                                        |
| ------------------------------- | ------------------------------------------------------------ |
| AWS_ACCESS_KEY_ID               | ASIAY24FZKAOHEXAMPLE                                         |
| AWS_DEFAULT_REGION              | ap-southeast-2                                               |
| AWS_LAMBDA_FUNCTION_MEMORY_SIZE | 1769                                                         |
| AWS_LAMBDA_FUNCTION_NAME        | test-Function-Oir9IIuvmE3E                                   |
| AWS_LAMBDA_FUNCTION_VERSION     | $LATEST                                                      |
| AWS_LAMBDA_INITIALIZATION_TYPE  | on-demand                                                    |
| AWS_LAMBDA_RUNTIME_API          | 127.0.0.1:9001                                               |
| AWS_REGION                      | ap-southeast-2                                               |
| AWS_SECRET_ACCESS_KEY           | Y8fuc8UvsbAO/JEXAMPLE+qEO2lasMzB                             |
| AWS_SESSION_TOKEN               | IQoJb3JpZ2lumFwLX...EXAMPLE                                  |
| LANG                            | en_US.UTF-8                                                  |
| LD_LIBRARY_PATH                 | /lib64:/usr/lib64:/var/runtime:/var/runtime/lib:/var/task:/var/task/lib:/opt/lib |
| PATH                            | /usr/local/bin:/usr/bin/:/bin:/opt/bin                       |
| TZ                              | :UTC                                                         |

_In addition to the above_, here are the environment variables that the function
runtime has:

| Name                       | Value                                                |
| -------------------------- | ---------------------------------------------------- |
| AWS_LAMBDA_LOG_GROUP_NAME  | /aws/lambda/test-Function-Oir9IIuvmE3E               |
| AWS_LAMBDA_LOG_STREAM_NAME | 2022/12/15/[$LATEST]534601edddcb4ad8a23042e2d6042f68 |
| AWS_XRAY_CONTEXT_MISSING   | LOG_ERROR                                            |
| AWS_XRAY_DAEMON_ADDRESS    | 169.254.79.129:2000                                  |
| LAMBDA_RUNTIME_DIR         | /var/runtime                                         |
| LAMBDA_TASK_ROOT           | /var/task                                            |
| _AWS_XRAY_DAEMON_ADDRESS   | 169.254.79.129                                       |
| _AWS_XRAY_DAEMON_PORT      | 2000                                                 |
| _HANDLER                   | myhandler                                            |

