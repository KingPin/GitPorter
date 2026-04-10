#!/bin/bash

#
# Script to mirror GitHub repos to a Gitea instance.
#
# Modes:
#   - Mirror a public/private repo
#   - Mirror all public/private repos of a user
#   - Mirror all starred repos by a user
#   - Mirror all public/private repos of an organization
#
# Improvements:
#   - Exponential backoff for GitHub API (handles 403/429 Rate Limits)
#   - Sleep timers between pagination to prevent hammering
#   - Retry logic for Gitea repo creation
#   - Explicit error handling for 422 (Allowed Domains) 
# 

# ENVs:
#   ACCESS_TOKEN = Gitea token
#   GITEA_URL    = Gitea URL
#   GITHUB_TOKEN = GitHub personal access token

# Pacing Settings
GITHUB_API_DELAY=2 # Seconds to wait between GitHub pagination requests
GITEA_API_DELAY=1  # Seconds to wait between creating repositories in Gitea

# Displays the given input including "=> " on the console.
log () {
	echo "=> $1"
}

# Removed -f so we can manually parse HTTP status codes for retries
CURL="curl -s -S --connect-timeout 10"

# Check for correctly set ENVs
if [[ -z "${ACCESS_TOKEN}" || -z "${GITEA_URL}" ]]; then
    echo -e "Please set the Gitea access token and URL in environment:\nexport ACCESS_TOKEN=abc\nexport GITEA_URL=http://gitea:3000\n" >&2
    echo -e "Don't use a trailing slash in URL!"
    exit 1
fi

# Parse input arguments
if [[ -z "$1" ]]; then
	log "No parameter(s) given. Exit."
    exit 1
fi
while [[ "$#" -gt 0 ]]; do
	case $1 in
		-m|--mode) mode="$2"; shift ;;
		-o|--org) gitea_organization="$2"; shift ;;
        -u|--user) github_user="$2"; shift ;;
        -v|--visibility) visibility="$2"; shift ;;
        -r|--repo) repo="$2"; shift ;;
		*) log "Unknown parameter passed: $1"; exit 1 ;;
	esac
	shift
done

fail_print_usage () {
    echo -e "Usage: $0"
    echo -e "   -m, --mode {org,star,repo,user}     Mode to use; either mirror an organization or mirror all starred repositories."
    echo -e "   -o, --org \$organization             GitHub organization to mirror and/or the target organization in Gitea."
    echo -e "   -u, --user \$github_user             GitHub user to gather the starred repositories from."
    echo -e "   -v, --visibility {public,private}   Visibility for the created Gitea organization."
    echo -e "   -r, --repo \$repo_url                GitHub URL of a single repo to create a mirror for."
    echo "" >&2
    exit 1;
}

# Parameter checks omitted for brevity (same as original)
if [[ -z "${mode}" ]]; then fail_print_usage; fi
if [ "${mode}" == "org" ] && [[ -z "${gitea_organization}" || -z "${visibility}" ]]; then fail_print_usage; fi
if [ "${mode}" == "star" ] && [[ -z "${gitea_organization}" || -z "${github_user}" ]]; then fail_print_usage; fi
if [ "${mode}" == "repo" ] && [[ -z "${repo}" || -z "${github_user}" ]]; then fail_print_usage; fi
if [ "${mode}" == "user" ] && [[ -z "${github_user}" ]]; then fail_print_usage; fi  

set -e pipefail

header_options=(-H  "Authorization: Bearer ${ACCESS_TOKEN}" -H "accept: application/json" -H "Content-Type: application/json")
jsonoutput=$(mktemp -d -t github-repos-XXXXXXXX)

trap "rm -rf ${jsonoutput}" EXIT

set_uid() {
    uid=$($CURL -f "${header_options[@]}" $GITEA_URL/api/v1/orgs/${gitea_organization} | jq .id)
}

set_uid_user() {
    uid=$($CURL -f "${header_options[@]}" $GITEA_URL/api/v1/users/${github_user} | jq .id)
}

# Helper function to fetch from GitHub with Exponential Backoff
fetch_github_paginated() {
    local base_url="$1"
    local auth_param="$2"
    local max_retries=5
    
    i=1
    while true; do
        local out_file="${jsonoutput}/${i}.json"
        local retry_delay=10
        local success=false
        
        for ((attempt=1; attempt<=max_retries; attempt++)); do
            local http_code
            if [[ -n "$auth_param" ]]; then
                http_code=$($CURL -w "%{http_code}" -o "$out_file" -u "$auth_param" "${base_url}page=${i}&per_page=100")
            else
                http_code=$($CURL -w "%{http_code}" -o "$out_file" "${base_url}page=${i}&per_page=100")
            fi
            
            if [[ "$http_code" == "200" ]]; then
                success=true
                break
            elif [[ "$http_code" == "403" || "$http_code" == "429" ]]; then
                log "Rate limited by GitHub! (HTTP $http_code). Sleeping for $retry_delay seconds before retry..."
                sleep $retry_delay
                retry_delay=$((retry_delay * 2)) # Exponential backoff
            else
                log "GitHub API error HTTP $http_code. Stopping fetch."
                break
            fi
        done
        
        if [[ "$success" != "true" ]]; then
            log "Failed to fetch page $i after $max_retries attempts. Exiting."
            exit 1
        fi
        
        # Check if empty array returned (end of pagination)
        if (( $(jq <"$out_file" '. | length') == 0 )); then
            rm -f "$out_file"
            break
        fi
        
        (( i++ ))
        sleep $GITHUB_API_DELAY # Pace the requests
    done
}

fetch_starred_repos() {
    log "Fetch starred repos."
    fetch_github_paginated "https://api.github.com/users/${github_user}/starred?" ""
}

fetch_orga_repos() {
    log "Fetch organization repos."
    fetch_github_paginated "https://api.github.com/orgs/${gitea_organization}/repos?" "username:${GITHUB_TOKEN}"
}

fetch_user_repos_owner() {
    log "Fetch user repos."
    fetch_github_paginated "https://api.github.com/user/repos?affiliation=owner&" "${github_user}:${GITHUB_TOKEN}"
}

fetch_user_repos_all() {
    log "Fetch user repos."
    fetch_github_paginated "https://api.github.com/users/${github_user}/repos?" "${github_user}:${GITHUB_TOKEN}"
}

fetch_one_repo() {
    log "Fetch one repo."
    repo=$(echo $repo | sed "s/https:\/\/github.com\///g" | sed "s/.git//g")
    $CURL -f "https://api.github.com/repos/$repo" -u "username:${GITHUB_TOKEN}" >${jsonoutput}/1.json
}

create_migration_repo() {
    local payload="$1"
    local max_attempts=3
    local retry_delay=5

    for ((attempt=1; attempt<=max_attempts; attempt++)); do
        local http_code
        http_code=$($CURL -w "%{http_code}" "${header_options[@]}" -d "$payload" -X POST $GITEA_URL/api/v1/repos/migrate -o ${jsonoutput}/result.txt)
        
        if [[ "$http_code" == "201" || "$http_code" == "200" ]]; then
            log "Successfully initiated migration."
            return 0
        elif [[ "$http_code" == "409" ]]; then
            log "Repo already exists in Gitea. Skipping."
            return 0
        elif [[ "$http_code" == "422" ]]; then
            log "ERROR 422: Validation Failed. Ensure 'github.com' is in ALLOWED_DOMAINS in your app.ini [migrations] section!"
            cat ${jsonoutput}/result.txt >&2
            echo ""
            return 1
        else
            log "Failed to create repo. HTTP $http_code. Retrying in $retry_delay seconds..."
            sleep $retry_delay
            retry_delay=$((retry_delay * 2))
        fi
    done
    log "Failed to migrate repo after $max_attempts attempts."
    return 1
}

create_migration_orga() {
    visibility="${1:-}"
    log "Create migration orga with name: ${gitea_organization}"
    local http_code
    http_code=$($CURL -w "%{http_code}" -X POST $GITEA_URL/api/v1/orgs "${header_options[@]}" --data '{"username": "'"${gitea_organization}"'", "visibility": "'"${visibility}"'"}' -o ${jsonoutput}/result.txt)
    
    if [[ "$http_code" != "201" && "$http_code" != "422" ]]; then
        log "Failed to create organization. HTTP $http_code"
        cat ${jsonoutput}/result.txt >&2
    fi
}

repos_to_migration() {
    log "Repos to migration started."
    for f in ${jsonoutput}/*.json; do
        [ -e "$f" ] || continue
        n=$(jq '. | length'<$f)
        if [[ "${n}" -gt "0" ]]; then
            (( n-- ))
        else
            continue;
        fi
        for i in $(seq 0 $n); do
            mig_data=$(jq -c ".[$i] | .uid=${uid} | \
                if(.visibility==\"private\") then .private=true else .private=false end |\
                if(.visibility==\"private\") then .auth_username=\"${github_user}\" else . end | \
                if(.visibility==\"private\") then .auth_password=\"${GITHUB_TOKEN}\" else . end | \
                .mirror=true | \
                .clone_addr=.clone_url | \
                .description=(.description // \"\")[0:255] | \
                .repo_name=.name | \
                {uid,repo_name,clone_addr,description,mirror,private,auth_username,auth_password}" <$f)
            
            echo "=> Migrating repo: $(jq -r ".[$i] | .name" <$f)"
            create_migration_repo "$mig_data"
            sleep $GITEA_API_DELAY # Pace the local requests
        done
    done
}

one_repo_to_migration() {
    log "One repo to migration started."
    for f in ${jsonoutput}/*.json; do
        [ -e "$f" ] || continue
        mig_data=$(jq -c ".repo_owner=\"${github_user}\" | \
            if(.visibility==\"private\") then .private=true else .private=false end |\
            if(.visibility==\"private\") then .auth_username=\"${github_user}\" else . end | \
            if(.visibility==\"private\") then .auth_password=\"${GITHUB_TOKEN}\" else . end | \
            .mirror=true | \
            .clone_addr=.clone_url | \
            .description=(.description // \"\")[0:255] | \
            .repo_name=.name | \
            {repo_owner,repo_name,clone_addr,description,mirror,private,auth_username,auth_password}" <$f)
        echo "=> Migrating repo: $(jq -r ".name" <$f)"
        create_migration_repo "$mig_data"
    done
}

if [ "${mode}" == "org" ]; then
    log "Mode = organization"
    fetch_orga_repos
    create_migration_orga ${visibility}
    set_uid
    repos_to_migration
elif [ "${mode}" == "repo" ]; then
    log "Mode = single repo"
    fetch_one_repo
    one_repo_to_migration
elif [ "${mode}" == "star" ]; then
    log "Mode = starred repos"
    set_uid
    fetch_starred_repos
    repos_to_migration
elif [ "${mode}" == "user" ]; then
    log "Mode = user"

    if [[ -z "${gitea_organization}" ]]; then
        log "Output = user"
        set_uid_user
        fetch_user_repos_owner
    else
        log "Output = organization"
        create_migration_orga ${visibility}
        set_uid
        fetch_user_repos_all
    fi

    repos_to_migration
fi

log "Finished."
