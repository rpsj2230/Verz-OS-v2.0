# Sourced, never run: one function, `merge_s3_identity`, for the preparation scripts of the
# overlays that keep an identity in the object store's access file.
#
# WHY IT IS A LIBRARY AND NOT A COPY IN EACH SCRIPT. `/opt/brain/settings/seaweedfs/s3.json` has
# more than one writer: the object store's own overlay puts the application's identity in it and
# the trace ledger's puts the ledger's. Until 2026-10-13 the ledger's preparation wrote the whole
# file from its one identity on every deploy, which removed the application's key the day an
# install switched the ledger on. Two scripts with two copies of "merge" is how one of them goes
# back to overwriting, so the merge is one function, and the work itself is
# `python -m brain.ops.s3_identities merge`, where it is tested.
#
# THE MERGE RUNS IN THE APPLICATION'S CONTAINER, which the step names in BRAIN_APP_CONTAINER and
# which is the one interpreter every server this step runs on is promised. The identity, with its
# secret, is the first line of standard input and the existing file is the rest, so nothing secret
# is an argument. printf is a shell builtin and puts nothing in a process list either.
#
# THE FILE IS REPLACED ONLY WHEN THE WHOLE MERGE SUCCEEDED: the result is written beside it and
# moved over it, and a refusal (a file nobody can read, the container missing) leaves the file as
# it was and returns non-zero, which leaves the overlay out of this deploy and removes nothing.
#
# A STORE THAT IS RUNNING IS RESTARTED, BUT ONLY WHEN THE FILE CHANGED. The store reads its access
# file when it starts. Merging the ledger's identity into a store the application already uses
# would otherwise leave the ledger refused until somebody restarted it, which reads as a ledger that
# is broken. A deploy that merges the identity already there changes nothing and restarts nothing.
#
# Needs: SETTINGS (the settings directory), BRAIN_APP_CONTAINER and BRAIN_APP_PROJECT, from the step.
#
# Task ids: M32.3.1.1, M32.1.1.1

# merge_s3_identity NAME ACCESS_KEY SECRET_KEY ACTIONS_AS_A_JSON_ARRAY
merge_s3_identity() {
  _s3_file="$SETTINGS/seaweedfs/s3.json"
  _s3_app="${BRAIN_APP_CONTAINER:?the step names the application container}"
  mkdir -p "$SETTINGS/seaweedfs"
  if ! {
    printf '{"name":"%s","access_key":"%s","secret_key":"%s","actions":%s}\n' "$1" "$2" "$3" "$4"
    if [ -f "$_s3_file" ]; then cat "$_s3_file"; fi
  } | docker exec -i "$_s3_app" python -m brain.ops.s3_identities merge > "$_s3_file.new"; then
    rm -f "$_s3_file.new"
    return 1
  fi
  # Nothing changed: the file, and the store reading it, are left exactly as they are, so a deploy
  # that merges the same identity again restarts nothing.
  if [ -f "$_s3_file" ] && cmp -s "$_s3_file.new" "$_s3_file"; then
    rm -f "$_s3_file.new"
    return 0
  fi
  # The container's user must read it, and the file is the store's own access list.
  chmod 0644 "$_s3_file.new"
  mv "$_s3_file.new" "$_s3_file"
  # A store reads its access file when it starts, so an identity added to a store that is already
  # running is not known to it until it restarts. The overlays' own project is named after the
  # application's, as apply.sh names it. A store that is not running reads the file when it starts.
  for _s3_store in $(docker ps -q \
      --filter "label=com.docker.compose.project=${BRAIN_APP_PROJECT:-none}-overlays" \
      --filter "label=com.docker.compose.service=seaweedfs"); do
    printf 'overlays: the object store is restarted once to read the identity just merged\n'
    docker restart "$_s3_store" >/dev/null ||
      printf 'overlays: the object store could not be restarted; it reads the new identity when it next starts\n'
  done
  return 0
}
