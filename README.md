# IAM
This repository is for managing authorization that resembles IAM in AWS.<br><br>
Specific requirements are as follows:
- A user may or may not have (a) group(s).
- A user can make a purchase to get a certain permission
- A group can make a group-level purchase by which the maximum amount of access permission given to the group is defined.
- A group can make customizable roles
    - The role can be assigned to a user when user is added to the group
    - As a user can potentially belong to multiple groups, the access permission should be appropriately granted/revoked


## Set up 
```
poetry install
```

## Update
```
poetry self update
```


## Formatting
```
make check
```