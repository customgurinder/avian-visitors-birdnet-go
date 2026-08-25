FROM nginx:1.27-alpine

# Bake the site config in (rather than bind-mounting it) so the stack has zero
# host bind mounts — this makes it deploy cleanly from a Git-based Portainer
# stack, a `docker compose up`, or any other orchestrator. ADAPTER_HOST/PORT
# are substituted from the environment at container start via the official
# image's /etc/nginx/templates mechanism.
COPY default.conf.template /etc/nginx/templates/default.conf.template
