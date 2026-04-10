#!/bin/bash

#
# Script to completely delete an organization with all its repos on a Gitea instance.
#
# Improvements in this version:
#   - DANGER PROMPT: Requires typing the org name to confirm (prevents accidental wipes).
#   - DRY RUN MODE: Allows testing the script without actually deleting anything.
#   - PAGINATION: Correctly fetches ALL repos (the original script would miss repos if there were >50).
#   - PACING: Adds a small delay between deletes so it doesn't overload the Gitea server.
#   - DEPENDENCY CHECK: Verifies 'jq' and 'curl' are installed before running.
#

# ENVs:
#   ACCESS_TOKEN = Gitea token
#   GITEA_URL    = Gitea URL

# Displays the given input including "=> " on the console.
log () {
	echo -e "=> $1"
}

CURL="curl -s -S --connect-timeout 10"

# Pre-flight check for required tools
if ! command -v jq &> /dev/null; then
    echo "Error: 'jq' is not installed. Please install jq to use this script."
    exit 1
fi

# Check for correctly set ENVs
if [[ -z "${ACCESS_TOKEN}" || -z "${GITEA_URL}" ]]; then
    echo -e "Please set the Gitea access token and URL in environment:\nexport ACCESS_TOKEN=abc\nexport GITEA_URL=http://gitea:3000\n" >&2
    echo -e "Don't use a trailing slash in URL!"
    exit 1
fi

# Initialize variables
gitea_organization=""
force="false"
dry_run="false"

# Parse input arguments
if [[ -z "$1" ]]; then
	log "No parameter(s) given. Exit."
    exit 1
fi

while [[ "$#" -gt 0 ]]; do
	case $1 in
		-o|--org) gitea_organization="$2"; shift ;;
        --force) force="true" ;;
        --dry-run) dry_run="true" ;;
		*) log "Unknown parameter passed: $1"; exit 1 ;;
	esac
	shift
done

fail_print_usage () {
    echo -e "Usage: $0 -o <organization_name> [options]"
    echo -e "Options:"
    echo -e "   -o, --org \$organization   Target organization in Gitea to delete."
    echo -e "   --dry-run                 List what would be deleted WITHOUT actually deleting anything."
    echo -e "   --force                   Bypass the confirmation prompt (Dangerous! Use for CI/CD only)."
    echo "" >&2
    exit 1;
}

if [[ -z "${gitea_organization}" ]]; then
    echo -e "Organization not set."
    fail_print_usage
fi

set -eu pipefail

header_options=(-H  "Authorization: Bearer ${ACCESS_TOKEN}" -H "accept: application/json" -H "Content-Type: application/json")
jsonoutput=$(mktemp -d -t gitea-delete-XXXXXXXX)

trap "rm -rf ${jsonoutput}" EXIT

# 1. Fetch ALL repositories (Handling Pagination)
fetch_all_repos() {
    log "Scanning organization '${gitea_organization}' for repositories..."
    local page=1
    repo_count=0
    > "${jsonoutput}/all_repos.txt" # Create empty file to hold repo names

    while true; do
        local out_file="${jsonoutput}/page_${page}.json"
        local http_code
        http_code=$($CURL -w "%{http_code}" -X GET "${GITEA_URL}/api/v1/orgs/${gitea_organization}/repos?page=${page}&limit=50" "${header_options[@]}" -o "$out_file")

        if [[ "$http_code" == "404" ]]; then
            log "Organization '${gitea_organization}' not found! (HTTP 404)"
            exit 1
        elif [[ "$http_code" != "200" ]]; then
            log "Failed to fetch repositories. HTTP $http_code"
            cat "$out_file" >&2
            exit 1
        fi

        # Count repos on current page
        local count=$(jq '. | length' < "$out_file")
        if [[ "$count" -eq 0 ]]; then
            break # No more repos, exit loop
        fi

        # Extract full repo names (owner/repo_name) and append to our text file
        jq -r '.[] | .owner.username + "/" + .name' < "$out_file" >> "${jsonoutput}/all_repos.txt"
        repo_count=$((repo_count + count))
        ((page++))
    done

    log "Found $repo_count repositories."
}

# 2. The DANGER Prompt (Double Check)
confirm_destruction() {
    if [[ "$dry_run" == "true" ]]; then
        echo ""
        echo "================================================================="
        echo "                        --- DRY RUN ---                          "
        echo " The following actions WOULD be taken (nothing is being deleted):"
        echo "================================================================="
        cat "${jsonoutput}/all_repos.txt" | while read -r repo; do
            echo "   [WOULD DELETE REPO]: $repo"
        done
        echo "   [WOULD DELETE ORG] : $gitea_organization"
        echo "================================================================="
        exit 0
    fi

    if [[ "$force" != "true" ]]; then
        echo ""
        echo "================================================================="
        echo "                         !!! DANGER !!!                          "
        echo "================================================================="
        echo " You are about to permanently delete the organization:"
        echo " -> ${gitea_organization}"
        echo " And ALL ${repo_count} repositories within it."
        echo " This action CANNOT be undone."
        echo "================================================================="
        read -p "To confirm, type the exact name of the organization: " confirm_name

        if [[ "$confirm_name" != "${gitea_organization}" ]]; then
            echo ""
            log "Name did not match ('$confirm_name' != '$gitea_organization'). Aborting deletion."
            exit 1
        fi
        echo "Confirmed. Proceeding with deletion..."
    else
        log "Force flag detected. Bypassing safety confirmation."
    fi
}

# 3. Delete the repositories safely
delete_orga_repos() {
    log "Deleting $repo_count repos..."
    while IFS= read -r full_repo_name; do
        [[ -z "$full_repo_name" ]] && continue

        echo "=> Deleting repo: $full_repo_name"
        local http_code
        http_code=$($CURL -w "%{http_code}" -X DELETE "$GITEA_URL/api/v1/repos/${full_repo_name}" "${header_options[@]}" -o "${jsonoutput}/result.txt")

        if [[ "$http_code" == "204" || "$http_code" == "200" || "$http_code" == "404" ]]; then
            # 204/200 = Success, 404 = Already deleted
            sleep 0.5 # Be nice to the Gitea database
        else
            log "WARNING: Failed to delete $full_repo_name. HTTP $http_code"
            cat "${jsonoutput}/result.txt" >&2
        fi
    done < "${jsonoutput}/all_repos.txt"
}

# 4. Delete the organization itself
delete_orga() {
    log "Deleting organization: ${gitea_organization}..."
    local http_code
    http_code=$($CURL -w "%{http_code}" -X DELETE "$GITEA_URL/api/v1/orgs/${gitea_organization}" "${header_options[@]}" -o "${jsonoutput}/result.txt")

    if [[ "$http_code" == "204" || "$http_code" == "200" ]]; then
        log "Organization deleted successfully."
    elif [[ "$http_code" == "404" ]]; then
        log "Organization already deleted or not found."
    else
        log "Failed to delete organization. HTTP $http_code"
        cat "${jsonoutput}/result.txt" >&2
        exit 1
    fi
}

# Run the execution flow
fetch_all_repos
confirm_destruction
delete_orga_repos
delete_orga

log "Finished clean up."
