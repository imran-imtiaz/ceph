# IBMCEPH-14682 Implementation Tracker

**Jira:** https://ibm-ceph.atlassian.net/browse/IBMCEPH-14682
**Ceph Tracker:** https://tracker.ceph.com/issues/77561
**Status:** In Review
**PR:** https://github.com/imran-imtiaz/ceph/pull/new/wip-rbd-cgsm-base-imran

## Implementation Summary
Added snapshot schedule APIs for RBD mirror groups and fixed status endpoint to match CLI behavior.

## Changes
1. **Service Methods** (`services/rbd.py`)
   - group_snapshot_schedule_add/remove/list/status/get_info

2. **REST Controller** (`controllers/rbd_mirror_group_snapshot_schedule.py`)
   - POST/DELETE/GET endpoints for schedule management

3. **Status Fix** (`controllers/rbd_mirror_group.py`)
   - Populate all peer sites, format state as "up+state"/"down+state"
   - Include images and snapshots arrays

## Testing
```bash
# Status API
curl GET /api/block/mirroring/pool/{pool}/group/{group}/status

# Schedule APIs
curl POST /api/block/mirroring/group/snapshot/schedule \
  -d '{"level_spec":"pool/group","interval":"1h"}'
curl GET /api/block/mirroring/group/snapshot/schedule/list
```

## Next Steps
- [ ] Create PR
- [ ] Code review
- [ ] Testing
- [ ] Merge