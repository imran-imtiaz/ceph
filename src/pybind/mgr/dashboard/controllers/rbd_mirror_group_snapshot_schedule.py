# -*- coding: utf-8 -*-

import json
import logging
from typing import Optional

from ..exceptions import DashboardException
from ..security import Scope
from ..services.rbd import RbdMirroringService
from . import APIDoc, APIRouter, Endpoint, EndpointDoc, ReadPermission, \
    RESTController, UpdatePermission, allow_empty_body

logger = logging.getLogger('controllers.rbd_mirror_group_snapshot_schedule')


RBD_MIRROR_GROUP_SNAPSHOT_SCHEDULE_SCHEMA = {
    "name": (str, "Group name"),
    "schedule_interval": ([{
        "interval": (str, "Schedule interval"),
        "start_time": (str, "Start time")
    }], "Schedule intervals"),
    "schedule_time": (str, "Next scheduled time")
}

RBD_MIRROR_GROUP_SNAPSHOT_SCHEDULE_LIST_SCHEMA = {
    "schedules": ([RBD_MIRROR_GROUP_SNAPSHOT_SCHEDULE_SCHEMA], "List of schedules")
}

RBD_MIRROR_GROUP_SNAPSHOT_SCHEDULE_STATUS_SCHEMA = {
    "scheduled_groups": ([{
        "schedule_time": (str, "Scheduled time"),
        "group": (str, "Group name")
    }], "Scheduled groups")
}


@APIRouter('/block/mirroring/group/snapshot/schedule', Scope.RBD_MIRRORING)
@APIDoc("RBD Mirror Group Snapshot Schedule Management API", "RbdMirrorGroupSnapshotSchedule")
class RbdMirrorGroupSnapshotSchedule(RESTController):
    """
    Controller for RBD mirror group snapshot schedule operations.
    Provides endpoints for adding, removing, listing, and getting status
    of snapshot schedules for mirror groups.
    """

    @Endpoint(method='POST')
    @UpdatePermission
    @allow_empty_body
    @EndpointDoc("Add a snapshot schedule for a mirror group",
                 parameters={
                     'level_spec': (str, 'Level specification (pool/namespace/group or pool/group)'),
                     'interval': (str, 'Schedule interval (e.g., 1h, 2d, 30m)'),
                     'start_time': (str, 'Optional start time for the schedule')
                 })
    def create(self, level_spec: str, interval: str, start_time: Optional[str] = None):
        """
        Add a snapshot schedule for a mirror group.

        :param level_spec: Level specification (pool/namespace/group or pool/group)
        :param interval: Schedule interval (e.g., '1h', '2d', '30m')
        :param start_time: Optional start time for the schedule
        """
        try:
            RbdMirroringService.group_snapshot_schedule_add(
                level_spec, interval, start_time
            )
            return {
                'message': f'Snapshot schedule added successfully for {level_spec}',
                'level_spec': level_spec,
                'interval': interval,
                'start_time': start_time
            }
        except Exception as e:
            raise DashboardException(
                msg=f'Failed to add snapshot schedule: {str(e)}',
                code='snapshot_schedule_add_failed',
                http_status_code=400,
                component='rbd'
            )

    @Endpoint(method='DELETE')
    @UpdatePermission
    @EndpointDoc("Remove a snapshot schedule from a mirror group",
                 parameters={
                     'level_spec': (str, 'Level specification (pool/namespace/group or pool/group)'),
                     'interval': (str, 'Optional schedule interval to remove specific schedule'),
                     'start_time': (str, 'Optional start time to remove specific schedule')
                 })
    def delete(self, level_spec: str, interval: Optional[str] = None,
               start_time: Optional[str] = None):
        """
        Remove a snapshot schedule from a mirror group.

        :param level_spec: Level specification (pool/namespace/group or pool/group)
        :param interval: Optional schedule interval to remove specific schedule
        :param start_time: Optional start time to remove specific schedule
        """
        try:
            RbdMirroringService.group_snapshot_schedule_remove(
                level_spec, interval, start_time
            )
            return {
                'message': f'Snapshot schedule removed successfully for {level_spec}',
                'level_spec': level_spec
            }
        except Exception as e:
            raise DashboardException(
                msg=f'Failed to remove snapshot schedule: {str(e)}',
                code='snapshot_schedule_remove_failed',
                http_status_code=400,
                component='rbd'
            )

    @Endpoint(method='GET', path='list')
    @ReadPermission
    @EndpointDoc("List snapshot schedules for mirror groups",
                 parameters={
                     'level_spec': (str, 'Optional level specification to filter results')
                 },
                 responses={200: RBD_MIRROR_GROUP_SNAPSHOT_SCHEDULE_LIST_SCHEMA})
    def list(self, level_spec: str = ''):
        """
        List snapshot schedules for mirror groups.

        :param level_spec: Optional level specification to filter results
        :return: List of snapshot schedules
        """
        try:
            result = RbdMirroringService.group_snapshot_schedule_list(level_spec)
            if result and len(result) > 1:
                try:
                    schedules = json.loads(result[1]) if result[1] else {}
                    return schedules
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse schedule list: {result[1]}")
                    return {}
            return {}
        except Exception as e:
            raise DashboardException(
                msg=f'Failed to list snapshot schedules: {str(e)}',
                code='snapshot_schedule_list_failed',
                http_status_code=500,
                component='rbd'
            )

    @Endpoint(method='GET', path='status')
    @ReadPermission
    @EndpointDoc("Get status of snapshot schedules for mirror groups",
                 parameters={
                     'level_spec': (str, 'Optional level specification to filter results')
                 },
                 responses={200: RBD_MIRROR_GROUP_SNAPSHOT_SCHEDULE_STATUS_SCHEMA})
    def status(self, level_spec: str = ''):
        """
        Get status of snapshot schedules for mirror groups.

        :param level_spec: Optional level specification to filter results
        :return: Status of snapshot schedules
        """
        try:
            result = RbdMirroringService.group_snapshot_schedule_status(level_spec)
            if result and len(result) > 1:
                try:
                    status = json.loads(result[1]) if result[1] else {}
                    return status
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse schedule status: {result[1]}")
                    return {}
            return {}
        except Exception as e:
            raise DashboardException(
                msg=f'Failed to get snapshot schedule status: {str(e)}',
                code='snapshot_schedule_status_failed',
                http_status_code=500,
                component='rbd'
            )

    @Endpoint(method='GET', path='info')
    @ReadPermission
    @EndpointDoc("Get merged snapshot schedule information for mirror groups",
                 parameters={
                     'level_spec': (str, 'Optional level specification to filter results')
                 },
                 responses={200: [RBD_MIRROR_GROUP_SNAPSHOT_SCHEDULE_SCHEMA]})
    def info(self, level_spec: str = ''):
        """
        Get merged snapshot schedule information (list + status) for mirror groups.

        :param level_spec: Optional level specification to filter results
        :return: Merged schedule information
        """
        try:
            schedule_info = RbdMirroringService.get_group_snapshot_schedule_info(level_spec)
            return schedule_info if schedule_info else []
        except Exception as e:
            raise DashboardException(
                msg=f'Failed to get snapshot schedule info: {str(e)}',
                code='snapshot_schedule_info_failed',
                http_status_code=500,
                component='rbd'
            )

# Made with Bob
