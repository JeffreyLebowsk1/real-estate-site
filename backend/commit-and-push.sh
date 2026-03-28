#!/bin/bash
set -e
cd ~/real-estate-site
git add -A
git commit -m "Add CRM backend, admin panel, carousel, assets folder, cloudflared fix"
git push origin copilot/setup-email-functionality
echo "push done"
