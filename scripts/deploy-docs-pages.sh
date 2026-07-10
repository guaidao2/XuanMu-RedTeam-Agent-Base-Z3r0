#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(git rev-parse --show-toplevel)"
DOCS_DIR="$ROOT_DIR/docs"
DIST_DIR="$DOCS_DIR/.vitepress/dist"
PAGES_REMOTE="origin"
PAGES_BRANCH="gh-pages"
PAGES_REMOTE_REF="refs/heads/$PAGES_BRANCH"
PAGES_WORKTREE="/tmp/z3r0-pages"
PAGES_KEEP_COMMITS=2
COMMIT_MESSAGE="docs: deploy github pages"

created_worktree=0
content_changed=0
history_rewritten=0
remote_commit=""

copy_pages_commit() {
  local source_commit="$1"
  local tree="$2"
  local parent="${3:-}"
  local args=("$tree")

  if [[ -n "$parent" ]]; then
    args+=("-p" "$parent")
  fi

  local author_name author_email author_date committer_name committer_email committer_date
  author_name="$(git -C "$PAGES_WORKTREE" show -s --format=%an "$source_commit")"
  author_email="$(git -C "$PAGES_WORKTREE" show -s --format=%ae "$source_commit")"
  author_date="$(git -C "$PAGES_WORKTREE" show -s --format=%aI "$source_commit")"
  committer_name="$(git -C "$PAGES_WORKTREE" show -s --format=%cn "$source_commit")"
  committer_email="$(git -C "$PAGES_WORKTREE" show -s --format=%ce "$source_commit")"
  committer_date="$(git -C "$PAGES_WORKTREE" show -s --format=%cI "$source_commit")"

  git -C "$PAGES_WORKTREE" log -1 --format=%B "$source_commit" | env \
    GIT_AUTHOR_NAME="$author_name" \
    GIT_AUTHOR_EMAIL="$author_email" \
    GIT_AUTHOR_DATE="$author_date" \
    GIT_COMMITTER_NAME="$committer_name" \
    GIT_COMMITTER_EMAIL="$committer_email" \
    GIT_COMMITTER_DATE="$committer_date" \
    git -C "$PAGES_WORKTREE" commit-tree "${args[@]}" -F -
}

trim_pages_history() {
  local commit_count
  commit_count="$(git -C "$PAGES_WORKTREE" rev-list --count HEAD)"

  if (( commit_count <= PAGES_KEEP_COMMITS )); then
    return
  fi

  echo "Rewriting $PAGES_BRANCH history to keep the latest $PAGES_KEEP_COMMITS commits..."

  local current_commit previous_commit current_tree previous_tree
  current_commit="$(git -C "$PAGES_WORKTREE" rev-parse HEAD)"
  previous_commit="$(git -C "$PAGES_WORKTREE" rev-parse HEAD^)"
  current_tree="$(git -C "$PAGES_WORKTREE" rev-parse "$current_commit^{tree}")"
  previous_tree="$(git -C "$PAGES_WORKTREE" rev-parse "$previous_commit^{tree}")"

  local new_previous_commit new_current_commit
  new_previous_commit="$(copy_pages_commit "$previous_commit" "$previous_tree")"
  new_current_commit="$(copy_pages_commit "$current_commit" "$current_tree" "$new_previous_commit")"

  git -C "$PAGES_WORKTREE" reset --hard "$new_current_commit" >/dev/null
  history_rewritten=1
}

cleanup() {
  local status=$?
  if [[ "$created_worktree" -eq 1 ]]; then
    git worktree remove "$PAGES_WORKTREE" --force >/dev/null 2>&1 || true
  fi
  exit "$status"
}
trap cleanup EXIT

if [[ -e "$PAGES_WORKTREE" ]]; then
  echo "Worktree path already exists: $PAGES_WORKTREE" >&2
  echo "Remove it and rerun this script." >&2
  exit 1
fi

echo "Building VitePress docs..."
(
  cd "$DOCS_DIR"
  npm run docs:build
)

touch "$DIST_DIR/.nojekyll"

echo "Preparing $PAGES_BRANCH worktree..."
remote_info="$(git ls-remote --heads "$PAGES_REMOTE" "$PAGES_BRANCH")"
if [[ -n "$remote_info" ]]; then
  remote_commit="${remote_info%%$'\t'*}"
  git fetch "$PAGES_REMOTE" "$PAGES_BRANCH"
  git worktree add --detach "$PAGES_WORKTREE" "FETCH_HEAD"
else
  git worktree add --detach "$PAGES_WORKTREE" HEAD
  git -C "$PAGES_WORKTREE" switch --orphan "$PAGES_BRANCH"
fi
created_worktree=1

echo "Replacing worktree contents with build output..."
git -C "$PAGES_WORKTREE" rm -rf . >/dev/null 2>&1 || true
find "$PAGES_WORKTREE" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
cp -a "$DIST_DIR"/. "$PAGES_WORKTREE"/

git -C "$PAGES_WORKTREE" add -A

if git -C "$PAGES_WORKTREE" diff --cached --quiet; then
  echo "No documentation content changes found."
else
  git -C "$PAGES_WORKTREE" commit -m "$COMMIT_MESSAGE"
  content_changed=1
fi

trim_pages_history

if [[ "$content_changed" -eq 0 && "$history_rewritten" -eq 0 ]]; then
  echo "No documentation changes to deploy."
  exit 0
fi

if [[ -n "$remote_commit" ]]; then
  git -C "$PAGES_WORKTREE" push --force-with-lease="$PAGES_REMOTE_REF:$remote_commit" "$PAGES_REMOTE" "HEAD:$PAGES_BRANCH"
else
  git -C "$PAGES_WORKTREE" push --force-with-lease="$PAGES_REMOTE_REF:" "$PAGES_REMOTE" "HEAD:$PAGES_BRANCH"
fi

echo "Published docs to $PAGES_REMOTE/$PAGES_BRANCH."
