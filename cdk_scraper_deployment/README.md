# cocli CDK

Scraper/IoT stack stays in the campaign AWS region (roadmap: us-east-1). SES
send lives in a **second stack**, `CocliEmailStack-<campaign>`, in
`[email].ses_region` (roadmap: us-west-1).

That email stack is a **recipe for the next client**, not a wrap of today's
live resources. `cdk deploy` on a *new* account/domain:

1. Creates the SES domain identity, MAIL FROM, and configuration set.
2. Outputs three DKIM CNAME name/value pairs and the bounce MX host.
3. You add those records at the client's DNS (GoDaddy, etc.). Leave apex MX
   on Exchange/Outlook if they already receive mail there. Merge
   `include:amazonses.com` into existing SPF.

Do **not** `cdk deploy` this stack onto roadmap's existing
`getretirementtaxanalyzer.com` identity: CloudFormation would create a
*new* identity or rotate Easy DKIM tokens and the current GoDaddy CNAMEs
would stop matching. Importing those live resources into CloudFormation
only attaches a lifecycle manager; it does not produce a replayable
record. The Python stack *is* the record.

```bash
cd cdk_scraper_deployment
cdk synth -c campaign=NEWCLIENT --profile THEIR_PROFILE
# then, only for a domain that is not already an SES identity:
cdk deploy CocliEmailStack-NEWCLIENT --profile THEIR_PROFILE -c campaign=NEWCLIENT
```

# Welcome to your CDK Python project!

This is a blank project for CDK development with Python.

The `cdk.json` file tells the CDK Toolkit how to execute your app.

This project is set up like a standard Python project.  The initialization
process also creates a virtualenv within this project, stored under the `.venv`
directory.  To create the virtualenv it assumes that there is a `python3`
(or `python` for Windows) executable in your path with access to the `venv`
package. If for any reason the automatic creation of the virtualenv fails,
you can create the virtualenv manually.

To manually create a virtualenv on MacOS and Linux:

```
$ python3 -m venv .venv
```

After the init process completes and the virtualenv is created, you can use the following
step to activate your virtualenv.

```
$ source .venv/bin/activate
```

If you are a Windows platform, you would activate the virtualenv like this:

```
% .venv\Scripts\activate.bat
```

Once the virtualenv is activated, you can install the required dependencies.

```
$ pip install -r requirements.txt
```

At this point you can now synthesize the CloudFormation template for this code.

```
$ cdk synth
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
