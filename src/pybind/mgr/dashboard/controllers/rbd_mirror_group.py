# -*- coding: utf-8 -*-

import logging
from functools import partial
from typing import Optional

import rbd

from ..exceptions import DashboardException
from ..security import Scope
from ..services.exception import handle_rados_error, handle_rbd_error, serialize_dashboard_exception
from ..services.rbd import rbd_call
from . import APIDoc, APIRouter, Endpoint, EndpointDoc, ReadPermission, \
    RESTController, Task, UpdatePermission, allow_empty_body

logger = logging.getLogger('controllers.rbd_mirror_group')


# pylint: disable=not-callable
def RbdMirrorGroupTask(name, metadata, wait_for):  # noqa: N802
    def composed_decorator(func):
        func = handle_rados_error('pool')(func)
        func = handle_rbd_error()(func)
        return Task("rbd/mirror_group/{}".format(name), metadata, wait_for,
                    partial(serialize_dashboard_exception, include_http_status=True))(func)
    return composed_decorator


RBD_MIRROR_GROUP_SCHEMA = {
    "state": (str, "Mirror state"),
    "mode": (str, "Mirror mode"),
    "global_id": (str, "Global ID"),
    "primary": (bool, "Is primary")
}

RBD_MIRROR_GROUP_STATUS_SCHEMA = {
    "name": (str, "Group name"),
    "global_id": (str, "Global ID"),
    "state": (str, "Mirror state (format: up+state or down+state)"),
    "description": (str, "Status description"),
    "last_update": (str, "Last update time"),
    "images": ([{
        "pool_id": (int, "Pool ID"),
        "image_id": (str, "Image ID"),
        "state": (str, "Image state"),
        "description": (str, "Image description")
    }], "Images in group"),
    "peer_sites": ([{
        "site_name": (str, "Site name"),
        "mirror_uuid": (str, "Mirror UUID"),
        "state": (str, "Site state (format: up+state or down+state)"),
        "description": (str, "Site description"),
        "last_update": (str, "Last update time"),
        "images": ([{
            "pool_id": (int, "Pool ID"),
            "image_id": (str, "Image ID"),
            "state": (str, "Image state"),
            "description": (str, "Image description")
        }], "Images at peer site")
    }], "Peer sites"),
    "snapshots": ([str], "Mirror snapshots (only for primary groups in snapshot mode)")
}


@APIRouter('/block/mirroring/pool/{pool_name}/group', Scope.RBD_MIRRORING)
@APIDoc("RBD Mirror Group Management API", "RbdMirrorGroup")
class RbdMirrorGroup(RESTController):
    """
    Controller for RBD mirror group operations.
    Provides endpoints for enabling, disabling, promoting, demoting,
    resyncing, and getting status of mirror groups.
    """

    RESOURCE_ID = "group_name"

    @handle_rbd_error()
    @handle_rados_error('pool')
    @EndpointDoc("Get mirror group information",
                 parameters={
                     'pool_name': (str, 'Pool name'),
                     'namespace': (str, 'Namespace (optional)'),
                     'group_name': (str, 'Group name')
                 },
                 responses={200: RBD_MIRROR_GROUP_SCHEMA})
    def get(self, pool_name: str, group_name: str, namespace: Optional[str] = None):
        """Get mirror group information."""
        def _get_info(ioctx):
            with rbd.Group(ioctx, group_name) as group:
                info = group.mirror_group_get_info()

                # Map state enum to string
                state_map = {
                    rbd.RBD_MIRROR_GROUP_DISABLED: 'disabled',
                    rbd.RBD_MIRROR_GROUP_ENABLED: 'enabled',
                    rbd.RBD_MIRROR_GROUP_DISABLING: 'disabling'
                }

                # Map mode enum to string
                mode_map = {
                    rbd.RBD_MIRROR_IMAGE_MODE_JOURNAL: 'journal',
                    rbd.RBD_MIRROR_IMAGE_MODE_SNAPSHOT: 'snapshot'
                }

                return {
                    'state': state_map.get(info.get('state'), 'unknown'),
                    'mode': mode_map.get(info.get('image_mode'), 'unknown'),
                    'global_id': info.get('global_id', ''),
                    'primary': info.get('primary', False)
                }

        return rbd_call(pool_name, namespace, _get_info)

    @RbdMirrorGroupTask('enable', {
        'pool_name': '{pool_name}',
        'group_name': '{group_name}'
    }, 2.0)
    @allow_empty_body
    @EndpointDoc("Enable mirroring for a group",
                 parameters={
                     'pool_name': (str, 'Pool name'),
                     'group_name': (str, 'Group name'),
                     'namespace': (str, 'Namespace (optional)'),
                     'mode': (str, "Mirror mode (default: 'snapshot')")
                 })
    def set(self, pool_name: str, group_name: str, namespace: Optional[str] = None,
            mode: str = 'snapshot'):
        """
        Enable mirroring for a group.

        :param pool_name: Pool name
        :param group_name: Group name
        :param namespace: Namespace (optional)
        :param mode: Mirror mode (default: 'snapshot')
        """
        def _enable(ioctx):
            mode_map = {
                'journal': rbd.RBD_MIRROR_IMAGE_MODE_JOURNAL,
                'snapshot': rbd.RBD_MIRROR_IMAGE_MODE_SNAPSHOT
            }

            if mode not in mode_map:
                raise DashboardException(
                    msg=f"Invalid mirror mode: {mode}",
                    code='invalid_mirror_mode',
                    http_status_code=400,
                    component='rbd'
                )

            with rbd.Group(ioctx, group_name) as group:
                group.mirror_group_enable(mode_map[mode])

        return rbd_call(pool_name, namespace, _enable)

    @Endpoint(method='POST', path='{group_name}/promote')
    @RbdMirrorGroupTask('promote', {
        'pool_name': '{pool_name}',
        'group_name': '{group_name}'
    }, 2.0)
    @UpdatePermission
    @EndpointDoc("Promote a mirror group to primary",
                 parameters={
                     'pool_name': (str, 'Pool name'),
                     'group_name': (str, 'Group name'),
                     'namespace': (str, 'Namespace (optional)'),
                     'force': (bool, 'Force promotion (optional)')
                 })
    def promote(self, pool_name: str, group_name: str, namespace: Optional[str] = None,
                force: bool = False):
        """
        Promote a group to primary for RBD mirroring.

        :param pool_name: Pool name
        :param group_name: Group name
        :param namespace: Namespace (optional)
        :param force: Force promotion even if not cleanly demoted
        """
        def _promote(ioctx):
            with rbd.Group(ioctx, group_name) as group:
                group.mirror_group_promote(force)

        return rbd_call(pool_name, namespace, _promote)

    @Endpoint(method='POST', path='{group_name}/demote')
    @RbdMirrorGroupTask('demote', {
        'pool_name': '{pool_name}',
        'group_name': '{group_name}'
    }, 2.0)
    @UpdatePermission
    @EndpointDoc("Demote a mirror group to non-primary",
                 parameters={
                     'pool_name': (str, 'Pool name'),
                     'group_name': (str, 'Group name'),
                     'namespace': (str, 'Namespace (optional)')
                 })
    def demote(self, pool_name: str, group_name: str, namespace: Optional[str] = None):
        """
        Demote a group to non-primary for RBD mirroring.

        :param pool_name: Pool name
        :param group_name: Group name
        :param namespace: Namespace (optional)
        """
        def _demote(ioctx):
            with rbd.Group(ioctx, group_name) as group:
                group.mirror_group_demote()

        return rbd_call(pool_name, namespace, _demote)

    @Endpoint(method='POST', path='{group_name}/resync')
    @RbdMirrorGroupTask('resync', {
        'pool_name': '{pool_name}',
        'group_name': '{group_name}'
    }, 2.0)
    @UpdatePermission
    @EndpointDoc("Force resync of a mirror group",
                 parameters={
                     'pool_name': (str, 'Pool name'),
                     'group_name': (str, 'Group name'),
                     'namespace': (str, 'Namespace (optional)')
                 })
    def resync(self, pool_name: str, group_name: str, namespace: Optional[str] = None):
        """
        Force resync to primary group for RBD mirroring.

        :param pool_name: Pool name
        :param group_name: Group name
        :param namespace: Namespace (optional)
        """
        def _resync(ioctx):
            with rbd.Group(ioctx, group_name) as group:
                group.mirror_group_resync()

        return rbd_call(pool_name, namespace, _resync)

    @Endpoint(method='GET', path='{group_name}/status')
    @ReadPermission
    @handle_rbd_error()
    @handle_rados_error('pool')
    @EndpointDoc("Get mirror group status",
                 parameters={
                     'pool_name': (str, 'Pool name'),
                     'group_name': (str, 'Group name'),
                     'namespace': (str, 'Namespace (optional)')
                 },
                 responses={200: RBD_MIRROR_GROUP_STATUS_SCHEMA})
    def status(self, pool_name: str, group_name: str, namespace: Optional[str] = None):
        """
        Get RBD mirroring status for a group.

        :param pool_name: Pool name
        :param group_name: Group name
        :param namespace: Namespace (optional)
        """
        def _get_status(ioctx):
            with rbd.Group(ioctx, group_name) as group:
                status = group.mirror_group_get_global_status()

                # Get mirror peers to populate unknown statuses
                # This ensures all configured peer sites appear in the response
                try:
                    mirror_peers = []
                    pool_ioctx = rbd_call(pool_name, None, lambda ctx: ctx)
                    rbd_inst = rbd.RBD()
                    mirror_peers = rbd_inst.mirror_peer_site_list(pool_ioctx)
                except Exception:
                    # If we can't get peers, continue with what we have
                    pass

                # Populate unknown mirror group site statuses
                # This mimics the CLI behavior from populate_unknown_mirror_group_site_statuses()
                site_statuses = status.get('site_statuses', [])
                existing_uuids = {site.get('mirror_uuid') for site in site_statuses}
                
                # Add placeholder entries for missing peer sites
                for peer in mirror_peers:
                    peer_uuid = peer.get('uuid', '')
                    if peer_uuid and peer_uuid not in existing_uuids:
                        site_statuses.append({
                            'mirror_uuid': peer_uuid,
                            'site_name': peer.get('site_name', ''),
                            'state': rbd.MIRROR_GROUP_STATUS_STATE_UNKNOWN,
                            'description': 'status not found',
                            'last_update': 0,
                            'up': False,
                            'mirror_images': {}
                        })

                # Map state enum to string
                state_map = {
                    rbd.MIRROR_GROUP_STATUS_STATE_UNKNOWN: 'unknown',
                    rbd.MIRROR_GROUP_STATUS_STATE_ERROR: 'error',
                    rbd.MIRROR_GROUP_STATUS_STATE_STARTING_REPLAY: 'starting_replay',
                    rbd.MIRROR_GROUP_STATUS_STATE_REPLAYING: 'replaying',
                    rbd.MIRROR_GROUP_STATUS_STATE_STOPPING_REPLAY: 'stopping_replay',
                    rbd.MIRROR_GROUP_STATUS_STATE_STOPPED: 'stopped'
                }

                # Find local status (for primary site info)
                local_status = None
                for site in site_statuses:
                    if site.get('mirror_uuid') == '':  # Local site has empty UUID
                        local_status = site
                        break

                # Format the status response
                result = {
                    'name': status.get('name', group_name),
                    'global_id': status.get('info', {}).get('global_id', ''),
                    'state': 'unknown',
                    'description': '',
                    'last_update': '',
                    'peer_sites': [],
                    'images': []
                }

                # Set local status if available
                if local_status:
                    state_enum = local_status.get('state', rbd.MIRROR_GROUP_STATUS_STATE_UNKNOWN)
                    state_str = state_map.get(state_enum, 'unknown')
                    up = local_status.get('up', False)
                    result['state'] = f"{'up' if up else 'down'}+{state_str}"
                    result['description'] = local_status.get('description', '')
                    result['last_update'] = str(local_status.get('last_update', ''))
                    
                    # Add images from local status
                    for (pool_id, image_id), image_status in local_status.get('mirror_images', {}).items():
                        result['images'].append({
                            'pool_id': pool_id,
                            'image_id': image_id,
                            'state': f"{'up' if image_status.get('up', False) else 'down'}+{state_map.get(image_status.get('state'), 'unknown')}",
                            'description': image_status.get('description', '')
                        })

                # Process peer site statuses (exclude local site)
                for site in site_statuses:
                    if site.get('mirror_uuid') == '':  # Skip local site
                        continue
                        
                    state_enum = site.get('state', rbd.MIRROR_GROUP_STATUS_STATE_UNKNOWN)
                    state_str = state_map.get(state_enum, 'unknown')
                    up = site.get('up', False)
                    
                    peer_site = {
                        'site_name': site.get('site_name', ''),
                        'mirror_uuid': site.get('mirror_uuid', ''),
                        'state': f"{'up' if up else 'down'}+{state_str}",
                        'description': site.get('description', ''),
                        'last_update': str(site.get('last_update', '')),
                        'images': []
                    }
                    
                    # Add images for this peer site
                    for (pool_id, image_id), image_status in site.get('mirror_images', {}).items():
                        peer_site['images'].append({
                            'pool_id': pool_id,
                            'image_id': image_id,
                            'state': f"{'up' if image_status.get('up', False) else 'down'}+{state_map.get(image_status.get('state'), 'unknown')}",
                            'description': image_status.get('description', '')
                        })
                    
                    result['peer_sites'].append(peer_site)

                # Add snapshots if this is a primary group in snapshot mode
                info = status.get('info', {})
                if info.get('primary') and info.get('mirror_image_mode') == rbd.RBD_MIRROR_IMAGE_MODE_SNAPSHOT:
                    try:
                        rbd_inst = rbd.RBD()
                        snaps = rbd_inst.group_snap_list(ioctx, group_name)
                        # Filter to only mirror snapshots
                        result['snapshots'] = [
                            snap.get('name', '') for snap in snaps
                            if snap.get('name', '').startswith('.mirror.')
                        ]
                    except Exception:
                        result['snapshots'] = []

                return result

        return rbd_call(pool_name, namespace, _get_status)

    @Endpoint(method='POST', path='{group_name}/snapshot')
    @RbdMirrorGroupTask('snapshot', {
        'pool_name': '{pool_name}',
        'group_name': '{group_name}'
    }, 2.0)
    @UpdatePermission
    @EndpointDoc("Create a mirror group snapshot",
                 parameters={
                     'pool_name': (str, 'Pool name'),
                     'group_name': (str, 'Group name'),
                     'namespace': (str, 'Namespace (optional)'),
                     'flags': (int, 'Snapshot flags (optional)')
                 })
    def snapshot(self, pool_name: str, group_name: str, namespace: Optional[str] = None,
                 flags: int = 0):
        """
        Create RBD mirroring group snapshot.

        :param pool_name: Pool name
        :param group_name: Group name
        :param namespace: Namespace (optional)
        :param flags: Snapshot creation flags
        """
        def _create_snapshot(ioctx):
            with rbd.Group(ioctx, group_name) as group:
                snap_id = group.mirror_group_create_snapshot(flags)
                return {'snapshot_id': snap_id}

        return rbd_call(pool_name, namespace, _create_snapshot)

    @RbdMirrorGroupTask('disable', {
        'pool_name': '{pool_name}',
        'group_name': '{group_name}'
    }, 2.0)
    @EndpointDoc("Disable mirroring for a group",
                 parameters={
                     'pool_name': (str, 'Pool name'),
                     'group_name': (str, 'Group name'),
                     'namespace': (str, 'Namespace (optional)'),
                     'force': (bool, 'Force disable even if not primary')
                 })
    def delete(self, pool_name: str, group_name: str, namespace: Optional[str] = None,
               force: bool = False):
        """
        Disable mirroring for a group.

        :param pool_name: Pool name
        :param group_name: Group name
        :param namespace: Namespace (optional)
        :param force: Force disable even if not primary
        """
        def _disable(ioctx):
            with rbd.Group(ioctx, group_name) as group:
                group.mirror_group_disable(force)

        return rbd_call(pool_name, namespace, _disable)

# Made with Bob
