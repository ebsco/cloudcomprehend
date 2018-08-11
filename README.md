# CloudComprehend
## Contents
- [Use](#use)
- [Formatting Parameters and Variables](#useful-script-parameters-and-variables)
- [Common Errors](#common-errors)
- [Requirements](#requires)
- [Lambda Deployment](#deploying-the-script-to-aws-lambda)
- [Resource List](#resources-included-in-diagram)

## Use
### Local
```
usage: visualize_network.py [-h] [--outdir DIRECTORY] [--stroke STROKE]
                            [--text LINE_HEIGHT] [--subcols SUB_COLS]
                            [--peercols PEER_COLS] [--fontl FONT_LARGE]
                            [--all] [--linelabels] [--rtconnections]
                            profile region vpc
```
- Ex: ```python visualize_network.py my-aws-account us-east-1 vpc-1234abcd```
- Then go to draw.io ([web](https://www.draw.io/) or [app](https://about.draw.io/integrations/#integrations_offline)) and select "Open Existing Diagram"
- Resources and their connections may require some reorganization
- Finalize document via "File" -> "Export as"

### AWS Lambda
- Change ```LAMBDA_INVOCATION = False``` to ```LAMBDA_INVOCATION = True```
- This will disable ```argparse``` and run the visualization script on all VPCs found in the current region
- Output xml files will be saved to ```/tmp```
- Output xml files will then be stored in the s3 bucket specified by stack parameter: ```"OutputBucket"```, Lambda Environment Variable: ```'OUTPUT_BUCKET'```.

## Useful script parameters and variables
### Positional arguments:
```
  profile   aws profile
  region    aws region
  vpc       vpc id
```

### Optional arguments:
```
  -h, --help            show help message and exit
  --outdir DIRECTORY    output save directory            Default: .
  --stroke STROKE       line stroke width                Default: 3
  --text LINE_HEIGHT    text line height                 Default: 20
  --subcols SUB_COLS    subnet alignment columns         Default: 3
  --peercols PEER_COLS  peer VPC alignment columns       Default: 1
  --fontl FONT_LARGE    large font size                  Default: 16
  --all, -a             show non associated resources
  --linelabels, -l      add connection labels
  --rtconnections, -c   add route table connections
```

### Script variables
- ```CONNECTIONS_ROUNDED``` [ 0 | 1 ]: Connections rounded if 1, connections with 90 degree corners if 0
- To update the column widths of Diagram Lists, adjust the following parameters:
  - ```DIAGRAM_COL_WIDTH_SMALL      = 70```
  - ```DIAGRAM_COL_WIDTH_NORMAL     = 100```
  - ```DIAGRAM_COL_WIDTH_OVERSIZED  = 240```
- Colors may be changed with different hexadecimal values
  - ```BLACK  = "#000000"```
  - ```GREEN  = "#00ff00"```
  - ```BLUE   = "#0000ff"```
  - ```RED    = "#ff0000"```
- AWS specific colors (shouldn't need to be modified)
  - ```ICON_ORANGE  = "#F58536"```
  - ```ICON_GOLD    = "#D9A741"```
- Peered VPC size
  - ```VPC_MIN_W = 200```
  - ```VPC_MIN_H = 120```
- Minimum Subnet Size (if not associated with NAT)
  - ```SUBNET_MIN_W = 340```
  - ```SUBNET_MIN_H = 80```
- Padding default (Applies to most elements of diagram formatting and shouldn't need to be changed)
  - ```PADDING = 60```
- VPC "gutter" dimension (space above and to the left of the VPC where tables go)
  - ```VPC_GUTTER_DIM = 700```
- Connection grouping spacing (space between each connecting line when grouped)
  - ```LINE_BUNDLE_SPACING = 10```
- Standard diagram font size
  - ```FONT_SIZE_NORMAL = 12```

### Lambda Specific Parameter Modification
If the script is automated through lambda, cmd line defaults (global vars initialized from the ```args``` namespace) can be modified by changing the values in ```get_configuration()``` within the ```DefaultLambdaNamespace``` object returned. Otherwise, global vars should be modified in the usual way.

## Common Errors
- ```KeyError: 'OUTPUT_BUCKET'``` : This error may appear if the script is run locally but ```LAMBDA_INVOCATION``` is set to True.
- ```botocore.exceptions.NoRegionError: You must specify a region.``` (see above)

## Requires
- AWS cli/boto3 authentication for desired account

### Imports
```python
import boto3
import xml.etree.cElementTree as ET
import math
import argparse
import os
import errno
```

## Deploying the Script to AWS Lambda
- Change ```LAMBDA_INVOCATION``` to ```True``` before code upload

### Lambda Configuration
- Schedule: ```rate(7 days)```
- Timeout: 60
- Memory: 128
- Runtime: Python 2.7
- Handler: ```visualize_network.lambda_handler```

## Resources included in Diagram
- Network Acl (and acl entries)
- Nat Gateways
- Subnets
- Internet Gateways
- VPC Endpoints
- Route Tables (and routes)
- AZs
- Peering Connections
- VPC(s)
- VPNs / VPN Gateways
- Flow logs
- Connections between resources
