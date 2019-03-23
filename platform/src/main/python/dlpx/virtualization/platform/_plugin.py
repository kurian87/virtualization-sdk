#
# Copyright (c) 2019 by Delphix. All rights reserved.
#

# -*- coding: utf-8 -*-

"""Plugin for the Virtualization Platform

This module contains a skeleton of a plugin that allows users to extend the Delphix Dynamic Data
Platform's support for external data sources. A plugin is composed of three different parts
that determine how each stage of a data source's virtualization should be performed:
DiscoveryOperations, LinkedOperations and VirtualOperations. These three classes contain all the
methods available during the process of discovery, direct or staged linking, and provisioning
virtual datasets. Let's see an example of how we can start writing a plugin that provides
an implementation for the "virtual.configure" plugin operation, which is executed during
provisioning a virtual dataset.

Before we start looking at implementations of plugin operations, we have to initialize the
plugin object. Let's say we're writing a plugin for a database called "my_db". We can initialize
the plugin object as such:

  from dlpx.virtualization.platform import Plugin

  my_db_plugin = Plugin()

Now, a plugin writer should write an implementation of their "virtual.configure" operation and
decorate the implementation method with a corresponding decorator. The decorator's name must
start with the name of the plugin object as assigned in the statement above:

  @my_db_plugin.virtual.configure()
  def my_configure_implementation(source, repository, snapshot):
    do_something()
    ...
    ## The rest of the implementation.
    return

Let's walk through what happens when invoke "@my_db_plugin.virtual.configure()":

1. my_db_plugin.virtual.configure() function is called. This function allows to pass arguments
   to a decorator. The "self" argument is automatically provided on an object method, hence we
   don't have to pass any arguments.
2. configure_decorator function takes my_configure_implementation function as an input and it saves
   a handle to the implementation on the VirtualOperations object under configure_impl property. Then,
   configure_decorator returns my_configure_implementation to make sure that we preserve the signature
   and metadata of the original implementation function.
3. configure_wrapper(configure_request) is a function that corresponds to the Virtualization
   Platform API  (see platform.proto) and it accepts a protobuf message as input argument,
   and it returns another protobuf message. This function is invoked by the Dynamic Data Platform
   runtime. For the details on the semantics of those protobuf message, see the section below
   entitled "Virtualization Platform API wrappers".
4. configure_wrapper unpacks the received configure_request protobuf message to provide input
   arguments to self.configure_impl method (which points to my_configure_implementation). Then,
   self.configure_impl is invoked with the input arguments.
5. self.configure_impl returns a config object that we pack into a protobuf message response
   and return it. The response will be sent back to the Dynamic Data Platform runtime.

Virtualization Platform API wrappers

The wrappers are the implementation of the Virtualization Platform API. They take
<OperationName>Request protobuf message as input and return <OperationName>Response,
e.g. ConfigureRequest and ConfigureResponse. The wrappers are called by the Dynamic Data Platform
runtime and      input *Request protobuf message, delegate to the user defined
method that has logic for the virtualization operation itself (such as configure), and craft
a response object.


Note on method level imports: In method imports are needed for plugin defined
modules (from generated.definitions). These imports will fail on a developer's
environment if they haven't generated them yet. If these were module level
imports, the import for dlpx.virtualization.platform.Plugin will more likely
fail. The internal methods should only be called by the platform so it's safe
to have the import in the methods as the objects will exist at runtime.
"""

import json
from dlpx.virtualization import common_pb2
from dlpx.virtualization import platform_pb2
from dlpx.virtualization.platform import VirtualSource
from dlpx.virtualization.platform import DirectSource
from dlpx.virtualization.platform import StagedSource
from dlpx.virtualization.platform import Mount


__all__ = ['Plugin']


class DiscoveryOperations(object):

    def __init__(self):
        self.repository_impl = None
        self.source_config_impl = None

    def repository(self):
        def repository_decorator(repository_impl):
            if self.repository_impl:
                raise RuntimeError("An implementation for discovery.repository() operation has "
                                   "already been defined.")
            self.repository_impl = repository_impl
            return repository_impl
        return repository_decorator

    def source_config(self):
        def source_config_decorator(source_config_impl):
            if self.source_config_impl:
                raise RuntimeError("An implementation for discovery.source_config() operation has "
                                   "already been defined.")
            self.source_config_impl = source_config_impl
            return source_config_impl
        return source_config_decorator

    def _internal_repository(self, request):
        """Repository discovery wrapper.

        Executed just after adding or refreshing an environment. This plugin
        operation is run prior to discovering source configs. This plugin operation
        returns a list of repositories installed on a environment.

        Discover the repositories on an environment given a source connection.

        Args:
            request (RepositoryDiscoveryRequest): Repository
            Discovery operation arguments.

        Returns:
            RepositoryDiscoveryResponse: The return value of repository discovery
            operation.
        """
        def to_protobuf(repository):
            parameters = common_pb2.PluginDefinedObject()
            parameters.json = json.dumps(repository.to_dict())
            repository_protobuf = common_pb2.Repository()
            repository_protobuf.parameters.CopyFrom(parameters)
            return repository_protobuf

        if not self.repository_impl:
                raise RuntimeError("An implementation for the discovery.repository() operation has "
                                   "not been defined.")

        repositories = self.repository_impl(
            source_connection=request.source_connection)
        repository_discovery_response = platform_pb2.RepositoryDiscoveryResponse()
        repository_protobuf_list = [to_protobuf(repo) for repo in repositories]
        repository_discovery_response.return_value.repositories.extend(repository_protobuf_list)
        return repository_discovery_response

    def _internal_source_config(self, request):
        """Source config discovery wrapper.

        Executed when adding or refreshing an environment. This plugin operation is
        run after discovering repositories and before persisting/updating repository
        and source config data in MDS. This plugin operation returns a list of source
        configs from a discovered repository.

        Discover the source configs on an environment given a discovered repository.

        Args:
            request (SourceConfigDiscoveryRequest): Source
            Config Discovery arguments.

        Returns:
            SourceConfigDiscoveryResponse: The return value of source config
            discovery operation.
        """
        # Reasoning for method imports are in this file's docstring.
        from generated.definitions import RepositoryDefinition

        def to_protobuf(source_config):
            parameters = common_pb2.PluginDefinedObject()
            parameters.json = json.dumps(source_config.to_dict())
            source_config_protobuf = common_pb2.SourceConfig()
            source_config_protobuf.parameters.CopyFrom(parameters)
            return source_config_protobuf

        repository_definition = RepositoryDefinition.from_dict(json.loads(request.repository.parameters.json))

        if not self.source_config_impl:
                raise RuntimeError("An implementation for the discovery.source_config() operation has "
                                   "not been defined.")

        source_configs = self.source_config_impl(
            source_connection=request.source_connection,
            repository=repository_definition)
        source_config_discovery_response = platform_pb2.SourceConfigDiscoveryResponse()
        source_config_protobuf_list = [to_protobuf(source_config) for source_config in source_configs]
        source_config_discovery_response.return_value.source_configs.extend(source_config_protobuf_list)
        return source_config_discovery_response


class LinkedOperations(object):

    def __init__(self):
        self.pre_snapshot_impl = None
        self.post_snapshot_impl = None
        self.start_staging_impl = None
        self.stop_staging_impl = None
        self.status_impl = None
        self.worker_impl = None
        self.mount_specification_impl = None

    def pre_snapshot(self):
        def pre_snapshot_decorator(pre_snapshot_impl):
            if self.pre_snapshot_impl:
                raise RuntimeError("An implementation for linked.pre_snapshot() operation has "
                                   "already been defined.")
            self.pre_snapshot_impl = pre_snapshot_impl
            return pre_snapshot_impl
        return pre_snapshot_decorator

    def post_snapshot(self):
        def post_snapshot_decorator(post_snapshot_impl):
            if self.post_snapshot_impl:
                raise RuntimeError("An implementation for linked.post_snapshot() operation has "
                                   "already been defined.")
            self.post_snapshot_impl = post_snapshot_impl
            return post_snapshot_impl
        return post_snapshot_decorator

    def start_staging(self):
        def start_staging_decorator(start_staging_impl):
            if self.start_staging_impl:
                raise RuntimeError("An implementation for linked.start_staging() operation has "
                                   "already been defined.")
            self.start_staging_impl = start_staging_impl
            return start_staging_impl
        return start_staging_decorator

    def stop_staging(self):
        def stop_staging_decorator(stop_staging_impl):
            if self.stop_staging_impl:
                raise RuntimeError("An implementation for linked.stop_staging() operation has "
                                   "already been defined.")
            self.stop_staging_impl = stop_staging_impl
            return stop_staging_impl
        return stop_staging_decorator

    def status(self):
        def status_decorator(status_impl):
            if self.status_impl:
                raise RuntimeError("An implementation for linked.status() operation has "
                                   "already been defined.")
            self.status_impl = status_impl
            return status_impl
        return status_decorator

    def worker(self):
        def worker_decorator(worker_impl):
            if self.worker_impl:
                raise RuntimeError("An implementation for linked.worker() operation has "
                                   "already been defined.")
            self.worker_impl = worker_impl
            return worker_impl
        return worker_decorator

    def mount_specification(self):
        def mount_specification_decorator(mount_specification_impl):
            if self.mount_specification_impl:
                raise RuntimeError("An implementation for linked.mount_specification() operation has "
                                   "already been defined.")
            self.mount_specification_impl = mount_specification_impl
            return mount_specification_impl
        return mount_specification_decorator

    def _internal_direct_pre_snapshot(self, request):
        """Pre Snapshot Wrapper for direct plugins.

        Executed before creating a snapshot. This plugin
        operation is run prior to creating a snapshot for a direct source.

        Run pre-snapshot operation for a direct source.

        Args:
           request (DirectPreSnapshotRequest): Pre Snapshot arguments.

        Returns:
           DirectPreSnapshotResponse: A response containing DirectPreSnapshotResult
           if successful or PluginErrorResult in case of an error.
        """
        # Reasoning for method imports are in this file's docstring.
        from generated.definitions import RepositoryDefinition
        from generated.definitions import LinkedSourceDefinition
        from generated.definitions import SourceConfigDefinition

        direct_source_definition = LinkedSourceDefinition.from_dict(json.loads(request.direct_source.linked_source.parameters.json))
        direct_source = DirectSource(guid=request.direct_source.linked_source.guid,
                                       connection=request.direct_source.connection,
                                       parameters=direct_source_definition)

        repository = RepositoryDefinition.from_dict(json.loads(request.repository.parameters.json))
        source_config = SourceConfigDefinition.from_dict(json.loads(request.source_config.parameters.json))

        if not self.pre_snapshot_impl:
                raise RuntimeError("An implementation for the linked.pre_snapshot() operation has "
                                   "not been defined.")
        self.pre_snapshot_impl(
            direct_source=direct_source,
            repository=repository,
            source_config=source_config)

        direct_pre_snapshot_response = platform_pb2.DirectPreSnapshotResponse()
        direct_pre_snapshot_response.return_value.CopyFrom(platform_pb2.DirectPreSnapshotResult())

        return direct_pre_snapshot_response


    def _internal_direct_post_snapshot(self, request):
        """Post Snapshot Wrapper for direct plugins.

        Executed after creating a snapshot. This plugin
        operation is run after creating a snapshot for a direct source.

        Run post-snapshot operation for a direct source.

        Args:
           request (DirectPostSnapshotRequest): Post Snapshot arguments.

        Returns:
           DirectPostSnapshotResponse: A response containing the return value -
           DirectPostSnapshotResult which has the snapshot metadata on success. In
           case of errors, response object will contain PluginErrorResult.
        """
        # Reasoning for method imports are in this file's docstring.
        from generated.definitions import RepositoryDefinition
        from generated.definitions import LinkedSourceDefinition
        from generated.definitions import SourceConfigDefinition

        def to_protobuf(snapshot):
            parameters = common_pb2.PluginDefinedObject()
            parameters.json = json.dumps(snapshot.to_dict())
            snapshot_protobuf = common_pb2.Snapshot()
            snapshot_protobuf.parameters.CopyFrom(parameters)
            return snapshot_protobuf

        direct_source_definition = LinkedSourceDefinition.from_dict(json.loads(request.direct_source.linked_source.parameters.json))
        direct_source = DirectSource(guid=request.direct_source.linked_source.guid,
                                       connection=request.direct_source.connection,
                                       parameters=direct_source_definition)

        repository = RepositoryDefinition.from_dict(json.loads(request.repository.parameters.json))
        source_config = SourceConfigDefinition.from_dict(json.loads(request.source_config.parameters.json))

        if not self.post_snapshot_impl:
                raise RuntimeError("An implementation for the linked.post_snapshot() operation has "
                                   "not been defined.")

        snapshot = self.post_snapshot_impl(
            direct_source=direct_source,
            repository=repository,
            source_config=source_config)

        direct_post_snapshot_response = platform_pb2.DirectPostSnapshotResponse()
        direct_post_snapshot_response.return_value.snapshot.CopyFrom(to_protobuf(snapshot))

        return direct_post_snapshot_response

    def _internal_staged_pre_snapshot(self, request):
        """Pre Snapshot Wrapper for staged plugins.

        Executed before creating a snapshot. This plugin
        operation is run prior to creating a snapshot for a staged source.

        Run pre-snapshot operation for a staged source.

        Args:
           request (StagedPreSnapshotRequest): Pre Snapshot arguments.

        Returns:
           StagedPreSnapshotResponse: A response containing StagedPreSnapshotResult
           if successful or PluginErrorResult in case of an error.
        """
        # Reasoning for method imports are in this file's docstring.
        from generated.definitions import RepositoryDefinition
        from generated.definitions import LinkedSourceDefinition
        from generated.definitions import SourceConfigDefinition

        # Presnapshot implementations are not required (although they are very common)
        if self.pre_snapshot_impl is not None:

            staged_source_definition = LinkedSourceDefinition.from_dict(json.loads(request.staged_source.linked_source.parameters.json))
            mount = Mount(remote_environment=request.staged_source.staged_mount.remote_environment,
                            mount_path=request.staged_source.staged_mount.mount_path,
                            shared_path=request.staged_source.staged_mount.shared_path)
            staged_source = StagedSource(guid=request.staged_source.linked_source.guid,
                                           connection=request.staged_source.connection,
                                           parameters=staged_source_definition,
                                           mount=mount)

            repository = RepositoryDefinition.from_dict(json.loads(request.repository.parameters.json))
            source_config = SourceConfigDefinition.from_dict(json.loads(request.source_config.parameters.json))

            self.pre_snapshot_impl(
                staged_source=staged_source,
                repository=repository,
                source_config=source_config)

        staged_pre_snapshot_response = platform_pb2.StagedPreSnapshotResponse()
        staged_pre_snapshot_response.return_value.CopyFrom(platform_pb2.StagedPreSnapshotResult())

        return staged_pre_snapshot_response


    def _internal_staged_post_snapshot(self, request):
        """Post Snapshot Wrapper for staged plugins.

        Executed after creating a snapshot. This plugin
        operation is run after creating a snapshot for a staged source.

        Run post-snapshot operation for a staged source.

        Args:
           request (StagedPostSnapshotRequest): Post Snapshot arguments.

        Returns:
           StagedPostSnapshotResponse: A response containing the return value -
           StagedPostSnapshotResult which has the snapshot metadata on success. In
           case of errors, response object will contain PluginErrorResult.
        """
        # Reasoning for method imports are in this file's docstring.
        from generated.definitions import RepositoryDefinition
        from generated.definitions import LinkedSourceDefinition
        from generated.definitions import SourceConfigDefinition

        def to_protobuf(snapshot):
            parameters = common_pb2.PluginDefinedObject()
            parameters.json = json.dumps(snapshot.to_dict())
            snapshot_protobuf = common_pb2.Snapshot()
            snapshot_protobuf.parameters.CopyFrom(parameters)
            return snapshot_protobuf

        staged_source_definition = LinkedSourceDefinition.from_dict(json.loads(request.staged_source.linked_source.parameters.json))
        mount = Mount(remote_environment=request.staged_source.staged_mount.remote_environment,
                        mount_path=request.staged_source.staged_mount.mount_path,
                        shared_path=request.staged_source.staged_mount.shared_path)
        staged_source = StagedSource(guid=request.staged_source.linked_source.guid,
                                       connection=request.staged_source.connection,
                                       parameters=staged_source_definition,
                                       mount=mount)

        repository = RepositoryDefinition.from_dict(json.loads(request.repository.parameters.json))
        source_config = SourceConfigDefinition.from_dict(json.loads(request.source_config.parameters.json))

        if not self.post_snapshot_impl:
                raise RuntimeError("An implementation for the linked.post_snapshot() operation has "
                                   "not been defined.")

        snapshot = self.post_snapshot_impl(
            staged_source=staged_source,
            repository=repository,
            source_config=source_config)

        staged_post_snapshot_response = platform_pb2.StagedPostSnapshotResponse()
        staged_post_snapshot_response.return_value.snapshot.CopyFrom(to_protobuf(snapshot))

        return staged_post_snapshot_response


    def _internal_start_staging(self, request):
        """Start staging Wrapper for staged plugins.

        Executed when enabling the staging source. This plugin
        operation is run to start the staging source as part
        of the enable operation.

        Run start operation for a staged source.

        Args:
           request (StartStagingRequest): Start arguments.

        Returns:
           StartStagingResponse: A response containing StartStagingResult
           if successful or PluginErrorResult in case of an error.
        """
        # Reasoning for method imports are in this file's docstring.
        from generated.definitions import RepositoryDefinition
        from generated.definitions import LinkedSourceDefinition
        from generated.definitions import SourceConfigDefinition

        # startStaging is not a required operation
        if self.start_staging_impl is not None:
            staged_source_definition = LinkedSourceDefinition.from_dict(json.loads(request.staged_source.linked_source.parameters.json))
            mount = Mount(remote_environment=request.staged_source.staged_mount.remote_environment,
                            mount_path=request.staged_source.staged_mount.mount_path,
                            shared_path=request.staged_source.staged_mount.shared_path)
            staged_source = StagedSource(guid=request.staged_source.linked_source.guid,
                                           connection=request.staged_source.connection,
                                           parameters=staged_source_definition,
                                           mount=mount)

            repository = RepositoryDefinition.from_dict(json.loads(request.repository.parameters.json))
            source_config = SourceConfigDefinition.from_dict(json.loads(request.source_config.parameters.json))

            self.start_staging_impl(
                staged_source=staged_source,
                repository=repository,
                source_config=source_config)

        start_staging_response = platform_pb2.StartStagingResponse()
        start_staging_response.return_value.CopyFrom(platform_pb2.StartStagingResult())

        return start_staging_response


    def _internal_stop_staging(self, request):
        """Stop staging Wrapper for staged plugins.

        Executed when disabling the staging source. This plugin
        operation is run to stop the staging source as part
        of the disable operation.

        Run stop operation for a staged source.

        Args:
           request (StopStagingRequest): Stop arguments.

        Returns:
           StopStagingResponse: A response containing StopStagingResult
           if successful or PluginErrorResult in case of an error.
        """
        # Reasoning for method imports are in this file's docstring.
        from generated.definitions import RepositoryDefinition
        from generated.definitions import LinkedSourceDefinition
        from generated.definitions import SourceConfigDefinition

        # startStaging is not a required operation
        if self.stop_staging_impl is not None:
            staged_source_definition = LinkedSourceDefinition.from_dict(json.loads(request.staged_source.linked_source.parameters.json))
            mount = Mount(remote_environment=request.staged_source.staged_mount.remote_environment,
                            mount_path=request.staged_source.staged_mount.mount_path,
                            shared_path=request.staged_source.staged_mount.shared_path)
            staged_source = StagedSource(guid=request.staged_source.linked_source.guid,
                                           connection=request.staged_source.connection,
                                           parameters=staged_source_definition,
                                           mount=mount)

            repository = RepositoryDefinition.from_dict(json.loads(request.repository.parameters.json))
            source_config = SourceConfigDefinition.from_dict(json.loads(request.source_config.parameters.json))

            self.stop_staging_impl(
                staged_source=staged_source,
                repository=repository,
                source_config=source_config)

        stop_staging_response = platform_pb2.StopStagingResponse()
        stop_staging_response.return_value.CopyFrom(platform_pb2.StopStagingResult())

        return stop_staging_response


    def _internal_status(self, request):
        """Staged Status Wrapper for staged plugins.

        Executed as part of several operations to get the status
        of a staged source - active or inactive.

        Run status operation for a staged source.

        Args:
           request (StagedStatusRequest): Post Snapshot arguments.

        Returns:
           StagedStatusResponse: A response containing the return value -
           StagedStatusResult which has active or inactive status. In
           case of errors, response object will contain PluginErrorResult.
        """
        # Reasoning for method imports are in this file's docstring.
        from generated.definitions import RepositoryDefinition
        from generated.definitions import LinkedSourceDefinition
        from generated.definitions import SourceConfigDefinition

        if not self.status_impl:
            # If no implementation is provided, the linked source is always active
            staged_status_response = platform_pb2.StagedStatusResponse()
            staged_status_response.return_value.status = platform_pb2.StagedStatusResult.ACTIVE
            return staged_status_response

        staged_source_definition = LinkedSourceDefinition.from_dict(json.loads(request.staged_source.linked_source.parameters.json))
        mount = Mount(remote_environment=request.staged_source.staged_mount.remote_environment,
                        mount_path=request.staged_source.staged_mount.mount_path,
                        shared_path=request.staged_source.staged_mount.shared_path)
        staged_source = StagedSource(guid=request.staged_source.linked_source.guid,
                                       connection=request.staged_source.connection,
                                       parameters=staged_source_definition,
                                       mount=mount)

        repository = RepositoryDefinition.from_dict(json.loads(request.repository.parameters.json))
        source_config = SourceConfigDefinition.from_dict(json.loads(request.source_config.parameters.json))

        status = self.status_impl(
            staged_source=staged_source,
            repository=repository,
            source_config=source_config)

        staged_status_response = platform_pb2.StagedStatusResponse()
        staged_status_response.return_value.status = status.value

        return staged_status_response


    def _internal_worker(self, request):
        """Staged Worker Wrapper for staged plugins.

        Executed as part of validated sync. This plugin
        operation is run to sync staging source as part
        of the validated sync operation.

        Run worker operation for a staged source.

        Args:
           request (StagedWorkerRequest): Worker arguments.

        Returns:
           StagedWorkerResponse: A response containing StagedWorkerResult
           if successful or PluginErrorResult in case of an error.
        """
        # Reasoning for method imports are in this file's docstring.
        from generated.definitions import RepositoryDefinition
        from generated.definitions import LinkedSourceDefinition
        from generated.definitions import SourceConfigDefinition

        # worker is not a required operation
        if self.worker_impl is not None:
            staged_source_definition = LinkedSourceDefinition.from_dict(json.loads(request.staged_source.linked_source.parameters.json))
            mount = Mount(remote_environment=request.staged_source.staged_mount.remote_environment,
                            mount_path=request.staged_source.staged_mount.mount_path,
                            shared_path=request.staged_source.staged_mount.shared_path)
            staged_source = StagedSource(guid=request.staged_source.linked_source.guid,
                                           connection=request.staged_source.connection,
                                           parameters=staged_source_definition,
                                           mount=mount)

            repository = RepositoryDefinition.from_dict(json.loads(request.repository.parameters.json))
            source_config = SourceConfigDefinition.from_dict(json.loads(request.source_config.parameters.json))

            self.worker_impl(
                staged_source=staged_source,
                repository=repository,
                source_config=source_config)

        staged_worker_response = platform_pb2.StagedWorkerResponse()
        staged_worker_response.return_value.CopyFrom(platform_pb2.StagedWorkerResult())

        return staged_worker_response

    def _internal_mount_specification(self, request):
        """Staged Mount/Ownership Spec Wrapper for staged plugins.

        Executed before creating a snapshot during sync or before enable/disable.
        This plugin operation is run before mounting datasets on staging to set
        the mount path and/or ownership.

        Run mount/ownership spec operation for a staged source.

        Args:
           request (StagedMountSpecRequest): Mount Spec arguments.

        Returns:
           StagedMountSpecResponse: A response containing the return value -
           StagedMountSpecResult which has the mount/ownership metadata on success.
           In case of errors, response object will contain PluginErrorResult.
        """
        # Reasoning for method imports are in this file's docstring.
        from generated.definitions import RepositoryDefinition
        from generated.definitions import LinkedSourceDefinition

        def to_protobuf_single_mount(single_mount):
            # Shared path is not supported for linked sources
            assert not single_mount.shared_path

            single_mount_protobuf = common_pb2.SingleEntireMount()
            single_mount_protobuf.mount_path = single_mount.mount_path
            single_mount_protobuf.remote_environment.CopyFrom(single_mount.remote_environment)

            return single_mount_protobuf

        def to_protobuf_ownership_spec(ownership_spec):
            ownership_spec_protobuf = common_pb2.OwnershipSpec()
            ownership_spec_protobuf.uid = ownership_spec.uid
            ownership_spec_protobuf.gid = ownership_spec.gid
            return ownership_spec_protobuf

        staged_source_definition = LinkedSourceDefinition.from_dict(json.loads(request.staged_source.linked_source.parameters.json))
        mount = Mount(remote_environment=request.staged_source.staged_mount.remote_environment,
                        mount_path=request.staged_source.staged_mount.mount_path,
                        shared_path=request.staged_source.staged_mount.shared_path)
        staged_source = StagedSource(guid=request.staged_source.linked_source.guid,
                                       connection=request.staged_source.connection,
                                       parameters=staged_source_definition,
                                       mount=mount)

        repository = RepositoryDefinition.from_dict(json.loads(request.repository.parameters.json))
        if not self.mount_specification_impl:
                raise RuntimeError("An implementation for the linked.mount_specification() operation has "
                                   "not been defined.")

        mount_spec = self.mount_specification_impl(
            staged_source=staged_source,
            repository=repository)

        # Only one mount is supported for linked sources
        mountLen = len(mount_spec.mounts)
        if mountLen != 1:
            raise RuntimeError("Exactly one mount must be provided for staging sources. Found {}".format(mountLen))

        staged_mount = to_protobuf_single_mount(mount_spec.mounts[0])

        staged_mount_spec_response = platform_pb2.StagedMountSpecResponse()
        staged_mount_spec_response.return_value.staged_mount.CopyFrom(staged_mount)

        # Ownership spec is optional for linked sources
        if mount_spec.ownership_specification:
            ownership_spec = to_protobuf_ownership_spec(mount_spec.ownership_specification)
            staged_mount_spec_response.return_value.ownership_spec.CopyFrom(ownership_spec)

        return staged_mount_spec_response


class VirtualOperations(object):

    def __init__(self):
        self.configure_impl = None
        self.unconfigure_impl = None
        self.reconfigure_impl = None
        self.start_impl = None
        self.stop_impl = None
        self.pre_snapshot_impl = None
        self.post_snapshot_impl = None
        self.status_impl = None
        self.initialize_impl = None
        self.mount_specification_impl = None

    def configure(self):
        def configure_decorator(configure_impl):
            if self.configure_impl:
                raise RuntimeError("An implementation for virtual.configure() operation has "
                                   "already been defined.")
            self.configure_impl = configure_impl
            return configure_impl
        return configure_decorator

    def unconfigure(self):
        def unconfigure_decorator(unconfigure_impl):
            if self.unconfigure_impl:
                raise RuntimeError("An implementation for virtual.unconfigure() operation has "
                                   "already been defined.")
            self.unconfigure_impl = unconfigure_impl
            return unconfigure_impl
        return unconfigure_decorator

    def reconfigure(self):
        def reconfigure_decorator(reconfigure_impl):
            if self.reconfigure_impl:
                raise RuntimeError("An implementation for virtual.reconfigure() operation has "
                                   "already been defined.")
            self.reconfigure_impl = reconfigure_impl
            return reconfigure_impl
        return reconfigure_decorator

    def start(self):
        def start_decorator(start_impl):
            if self.start_impl:
                raise RuntimeError("An implementation for virtual.start() operation has "
                                   "already been defined.")
            self.start_impl = start_impl
            return start_impl
        return start_decorator

    def stop(self):
        def stop_decorator(stop_impl):
            if self.stop_impl:
                raise RuntimeError("An implementation for virtual.stop() operation has "
                                   "already been defined.")
            self.stop_impl = stop_impl
            return stop_impl
        return stop_decorator

    def pre_snapshot(self):
        def pre_snapshot_decorator(pre_snapshot_impl):
            if self.pre_snapshot_impl:
                raise RuntimeError("An implementation for virtual.pre_snapshot() operation has "
                                   "already been defined.")
            self.pre_snapshot_impl = pre_snapshot_impl
            return pre_snapshot_impl
        return pre_snapshot_decorator

    def post_snapshot(self):
        def post_snapshot_decorator(post_snapshot_impl):
            if self.post_snapshot_impl:
                raise RuntimeError("An implementation for virtual.post_snapshot() operation has "
                                   "already been defined.")
            self.post_snapshot_impl = post_snapshot_impl
            return post_snapshot_impl
        return post_snapshot_decorator

    def status(self):
        def status_decorator(status_impl):
            if self.status_impl:
                raise RuntimeError("An implementation for virtual.status() operation has "
                                   "already been defined.")
            self.status_impl = status_impl
            return status_impl
        return status_decorator

    def initialize(self):
        def initialize_decorator(initialize_impl):
            if self.initialize_impl:
                raise RuntimeError("An implementation for virtual.initialize() operation has "
                                   "already been defined.")
            self.initialize_impl = initialize_impl
            return initialize_impl
        return initialize_decorator

    def mount_specification(self):
        def mount_specification_decorator(mount_specification_impl):
            if self.mount_specification_impl:
                raise RuntimeError("An implementation for virtual.mount_specification() operation has "
                                   "already been defined.")
            self.mount_specification_impl = mount_specification_impl
            return mount_specification_impl
        return mount_specification_decorator

    def _internal_configure(self, request):
        """Configure operation wrapper.

        Executed just after cloning the captured data and mounting it to a target
        environment. Specifically, this plugin operation is run during provision and
        refresh, prior to taking the initial snapshot of the clone. This plugin
        operation is run before the user-customizable Configure Clone and Before
        Refresh operations are run. It must return a sourceConfig object that
        represents the new dataset.

        Configure the data to be usable on the target environment. For database data
        files, this may mean recovering from a crash consistent format or backup.
        For application files, this may mean reconfiguring XML files or rewriting
        hostnames and symlinks.

        Args:
          request (ConfigureRequest): Configure operation arguments.

        Returns:
          ConfigureResponse: A response containing the return value of the
          configure operation, as a ConfigureResult.
        """
        # Reasoning for method imports are in this file's docstring.
        from generated.definitions import VirtualSourceDefinition
        from generated.definitions import RepositoryDefinition
        from generated.definitions import SnapshotDefinition

        virtual_source_definition = VirtualSourceDefinition.from_dict(json.loads(request.virtual_source.parameters.json))

        virtual_source = VirtualSource(guid=request.virtual_source.guid,
                                       connection=request.virtual_source.connection,
                                       parameters=virtual_source_definition)

        repository = RepositoryDefinition.from_dict(json.loads(request.repository.parameters.json))
        snapshot = SnapshotDefinition.from_dict(json.loads(request.snapshot.parameters.json))

        if not self.configure_impl:
            raise RuntimeError("An implementation the for virtual.configure() operation has "
                                   "not been defined.")

        config = self.configure_impl(
            virtual_source=virtual_source,
            repository=repository,
            snapshot=snapshot)
        configure_response = platform_pb2.ConfigureResponse()
        configure_response.return_value.source_config.parameters.json = json.dumps(config.to_dict())
        return configure_response

    def _internal_unconfigure(self, request):
        """Unconfigure operation wrapper.

        Executed when disabling or deleting an existing virtual source which has already
        been mounted to a target environment. This plugin operation is run before
        unmounting the virtual source from the target environment.

        Args:
          request (UnconfigureRequest): Unconfigure operation arguments.

        Returns:
          UnconfigureResponse: A response containing UnconfigureResult
           if successful or PluginErrorResult in case of an error.
        """
        # Reasoning for method imports are in this file's docstring.
        from generated.definitions import VirtualSourceDefinition
        from generated.definitions import RepositoryDefinition
        from generated.definitions import SourceConfigDefinition

        if self.unconfigure_impl is not None:
            virtual_source_definition = VirtualSourceDefinition.from_dict(json.loads(request.virtual_source.parameters.json))
            virtual_source = VirtualSource(guid=request.virtual_source.guid,
                                           connection=request.virtual_source.connection,
                                           parameters=virtual_source_definition)

            repository = RepositoryDefinition.from_dict(json.loads(request.repository.parameters.json))
            source_config = SourceConfigDefinition.from_dict(json.loads(request.source_config.parameters.json))

            self.unconfigure_impl(
                repository=repository,
                source_config=source_config,
                virtual_source=virtual_source)
        unconfigure_response = platform_pb2.UnconfigureResponse()
        unconfigure_response.return_value.CopyFrom(platform_pb2.UnconfigureResult())
        return unconfigure_response


    def _internal_reconfigure(self, request):
        """Reconfigure operation wrapper.

        Executed while attaching a VDB during a virtual source enable job and returns
        a virtual source config.

        Args:
          request (ReconfigureRequest): Reconfigure operation arguments.

        Returns:
          ReconfigureResponse: A response containing the return value of the
          reconfigure operation, as a ReconfigureResult.
        """
        # Reasoning for method imports are in this file's docstring.
        from generated.definitions import VirtualSourceDefinition
        from generated.definitions import SnapshotDefinition
        from generated.definitions import SourceConfigDefinition

        virtual_source_definition = VirtualSourceDefinition.from_dict(json.loads(request.virtual_source.parameters.json))
        virtual_source = VirtualSource(guid=request.virtual_source.guid,
                                       connection=request.virtual_source.connection,
                                       parameters=virtual_source_definition)

        snapshot = SnapshotDefinition.from_dict(json.loads(request.snapshot.parameters.json))
        source_config = SourceConfigDefinition.from_dict(json.loads(request.source_config.parameters.json))

        if not self.reconfigure_impl:
            raise RuntimeError("An implementation for the virtual.reconfigure() operation has "
                                   "not been defined.")

        config = self.reconfigure_impl(
            snapshot=snapshot,
            source_config=source_config,
            virtual_source=virtual_source)
        reconfigure_response = platform_pb2.ReconfigureResponse()
        reconfigure_response.return_value.source_config.parameters.json = json.dumps(config.to_dict())
        return reconfigure_response


    def _internal_start(self, request):
        """Start operation wrapper.

        Executed after attaching a VDB during a virtual source enable job to start
        the database.

        Args:
          request (StartRequest): Start operation arguments.

        Returns:
          StartResponse: A response containing StartResult if successful or
          PluginErrorResult in case of an error.
        """
        # Reasoning for method imports are in this file's docstring.
        from generated.definitions import VirtualSourceDefinition
        from generated.definitions import RepositoryDefinition
        from generated.definitions import SourceConfigDefinition

        if self.start_impl is not None:
            virtual_source_definition = VirtualSourceDefinition.from_dict(json.loads(request.virtual_source.parameters.json))
            virtual_source = VirtualSource(guid=request.virtual_source.guid,
                                           connection=request.virtual_source.connection,
                                           parameters=virtual_source_definition)

            repository = RepositoryDefinition.from_dict(json.loads(request.repository.parameters.json))
            source_config = SourceConfigDefinition.from_dict(json.loads(request.source_config.parameters.json))

            self.start_impl(
                repository=repository,
                source_config=source_config,
                virtual_source=virtual_source)
        start_response = platform_pb2.StartResponse()
        start_response.return_value.CopyFrom(platform_pb2.StartResult())
        return start_response


    def _internal_stop(self, request):
        """Stop operation wrapper.

        Executed before unmounting a VDB during a virtual source stop job.

        Args:
          request (StopRequest): Stop operation arguments.

        Returns:
          StopResponse: A response containing StopResult if successful or
          PluginErrorResult in case of an error.
        """
        # Reasoning for method imports are in this file's docstring.
        from generated.definitions import VirtualSourceDefinition
        from generated.definitions import RepositoryDefinition
        from generated.definitions import SourceConfigDefinition

        if self.stop_impl is not None:
            virtual_source_definition = VirtualSourceDefinition.from_dict(json.loads(request.virtual_source.parameters.json))
            virtual_source = VirtualSource(guid=request.virtual_source.guid,
                                           connection=request.virtual_source.connection,
                                           parameters=virtual_source_definition)

            repository = RepositoryDefinition.from_dict(json.loads(request.repository.parameters.json))
            source_config = SourceConfigDefinition.from_dict(json.loads(request.source_config.parameters.json))

            self.stop_impl(
                repository=repository,
                source_config=source_config,
                virtual_source=virtual_source)

        stop_response = platform_pb2.StopResponse()
        stop_response.return_value.CopyFrom(platform_pb2.StopResult())
        return stop_response


    def _internal_pre_snapshot(self, request):
        """Virtual pre snapshot operation wrapper.

        Executed before creating a ZFS snapshot. This plugin operation is run prior to
        creating a snapshot for a virtual source.

        Run pre-snapshot operation for a virtual source.

        Args:
          virtual_pre_snapshot_request (VirtualPreSnapshotRequest):
          Virtual pre snapshot operation arguments.

        Returns:
          VirtualPreSnapshotResponse: A response containing VirtualPreSnapshotResult
          if successful or PluginErrorResult in case of an error.
        """
        # Reasoning for method imports are in this file's docstring.
        from generated.definitions import VirtualSourceDefinition
        from generated.definitions import RepositoryDefinition
        from generated.definitions import SourceConfigDefinition

        if self.pre_snapshot_impl is not None:
            virtual_source_definition = VirtualSourceDefinition.from_dict(json.loads(request.virtual_source.parameters.json))
            virtual_source = VirtualSource(guid=request.virtual_source.guid,
                                           connection=request.virtual_source.connection,
                                           parameters=virtual_source_definition)

            repository = RepositoryDefinition.from_dict(json.loads(request.repository.parameters.json))
            source_config = SourceConfigDefinition.from_dict(json.loads(request.source_config.parameters.json))


            self.pre_snapshot_impl(
                repository=repository,
                source_config=source_config,
                virtual_source=virtual_source)

        virtual_pre_snapshot_response = platform_pb2.VirtualPreSnapshotResponse()
        virtual_pre_snapshot_response.return_value.CopyFrom(platform_pb2.VirtualPreSnapshotResult())
        return virtual_pre_snapshot_response


    def _internal_post_snapshot(self, request):
        """Virtual post snapshot operation wrapper.

        Executed after creating a ZFS snapshot. This plugin operation is run after
        creating a snapshot for a virtual source.

        Run post-snapshot operation for a virtual source.

        Args:
          request (VirtualPostSnapshotRequest): Virtual post snapshot operation arguments.

        Returns:
          VirtualPostSnapshotResponse: A response containing the return value of the
          virtual post snapshot operation, as a VirtualPostSnapshotResult.
        """
        # Reasoning for method imports are in this file's docstring.
        from generated.definitions import VirtualSourceDefinition
        from generated.definitions import RepositoryDefinition
        from generated.definitions import SourceConfigDefinition

        def to_protobuf(snapshot):
            parameters = common_pb2.PluginDefinedObject()
            parameters.json = json.dumps(snapshot.to_dict())
            snapshot_protobuf = common_pb2.Snapshot()
            snapshot_protobuf.parameters.CopyFrom(parameters)
            return snapshot_protobuf

        virtual_source_definition = VirtualSourceDefinition.from_dict(json.loads(request.virtual_source.parameters.json))
        virtual_source = VirtualSource(guid=request.virtual_source.guid,
                                       connection=request.virtual_source.connection,
                                       parameters=virtual_source_definition)

        repository = RepositoryDefinition.from_dict(json.loads(request.repository.parameters.json))
        source_config = SourceConfigDefinition.from_dict(json.loads(request.source_config.parameters.json))

        if not self.post_snapshot_impl:
            raise RuntimeError("An implementation for the virtual.post_snapshot() operation has "
                                   "not been defined.")

        snapshot = self.post_snapshot_impl(
            repository=repository,
            source_config=source_config,
            virtual_source=virtual_source)
        virtual_post_snapshot_response = platform_pb2.VirtualPostSnapshotResponse()
        virtual_post_snapshot_response.return_value.snapshot.CopyFrom(to_protobuf(snapshot))
        return virtual_post_snapshot_response


    def _internal_status(self, request):
        """Virtual status operation wrapper.

        Executed to get the status of a virtual source - active or inactive.

        Run status operation for a virtual source.

        Args:
          request (VirtualStatusRequest):
          Virtual status operation arguments.

        Returns:
          VirtualStatusResponse: A response containing VirtualStatusResult
          if successful or PluginErrorResult in case of an error.
        """
        # Reasoning for method imports are in this file's docstring.
        from generated.definitions import VirtualSourceDefinition
        from generated.definitions import RepositoryDefinition
        from generated.definitions import SourceConfigDefinition

        if not self.status_impl:
            virtual_status_response = platform_pb2.VirtualStatusResponse()
            virtual_status_response.return_value.status = platform_pb2.VirtualStatusResponse.ACTIVE
            return virtual_status_response

        virtual_source_definition = VirtualSourceDefinition.from_dict(json.loads(request.virtual_source.parameters.json))
        virtual_source = VirtualSource(guid=request.virtual_source.guid,
                                       connection=request.virtual_source.connection,
                                       parameters=virtual_source_definition)

        repository = RepositoryDefinition.from_dict(json.loads(request.repository.parameters.json))
        source_config = SourceConfigDefinition.from_dict(json.loads(request.source_config.parameters.json))

        virtual_status = self.status_impl(
            repository=repository,
            source_config=source_config,
            virtual_source=virtual_source)
        virtual_status_response = platform_pb2.VirtualStatusResponse()
        virtual_status_response.return_value.status = virtual_status.value
        return virtual_status_response


    def _internal_initialize(self, request):
        """Initialize operation wrapper.

        Executed during VDB creation after mounting onto the target environment.

        Run initialize operation for an empty virtual source.

        Args:
          request (InitializeRequest): Initialize operation arguments.

        Returns:
          InitializeResponse: A response containing InitializeResult
          if successful or PluginErrorResult in case of an error.
        """
        # Reasoning for method imports are in this file's docstring.
        from generated.definitions import VirtualSourceDefinition
        from generated.definitions import RepositoryDefinition
        from generated.definitions import SourceConfigDefinition

        virtual_source_definition = VirtualSourceDefinition.from_dict(json.loads(request.virtual_source.parameters.json))
        virtual_source = VirtualSource(guid=request.virtual_source.guid,
                                       connection=request.virtual_source.connection,
                                       parameters=virtual_source_definition)

        repository = RepositoryDefinition.from_dict(json.loads(request.repository.parameters.json))
        source_config = SourceConfigDefinition.from_dict(json.loads(request.source_config.parameters.json))

        if not self.initialize_impl:
            raise RuntimeError("An implementation for the virtual.initialize() operation has "
                                   "not been defined.")

        self.initialize_impl(
            repository=repository,
            source_config=source_config,
            virtual_source=virtual_source)
        initialize_response = platform_pb2.InitializeResponse()
        initialize_response.return_value.CopyFrom(platform_pb2.InitializeResult())
        return initialize_response


    def _internal_mount_specification(self, request):
        """Virtual mount spec operation wrapper.

        Executed to fetch the ownership spec before mounting onto a target environment.

        Run mount spec operation for a virtual source.

        Args:
          virtual_mount_spec_request (VirtualMountSpecRequest):
          Virtual mount spec operation arguments.

        Returns:
          VirtualMountSpecResponse: A response containing the return value of the
          virtual mount spec operation, as a VirtualMountSpecResult.
        """
        # Reasoning for method imports are in this file's docstring.
        from generated.definitions import VirtualSourceDefinition
        from generated.definitions import RepositoryDefinition

        def to_protobuf_single_mount(single_mount):
            single_mount_protobuf = common_pb2.SingleSubsetMount()

            host_protobuf = common_pb2.RemoteHost()
            host_protobuf.name = single_mount.remote_environment.host.name
            host_protobuf.reference = single_mount.remote_environment.host.reference
            host_protobuf.binary_path = single_mount.remote_environment.host.binary_path
            host_protobuf.scratch_path = single_mount.remote_environment.host.scratch_path

            environment_protobuf = common_pb2.RemoteEnvironment()
            environment_protobuf.name = single_mount.remote_environment.name
            environment_protobuf.reference = single_mount.remote_environment.reference
            environment_protobuf.host.CopyFrom(host_protobuf)

            single_mount_protobuf.remote_environment.CopyFrom(environment_protobuf)
            single_mount_protobuf.mount_path = single_mount.mount_path

            if single_mount.shared_path:
                single_mount_protobuf.shared_path = single_mount.shared_path

            return single_mount_protobuf

        def to_protobuf_ownership_spec(ownership_spec):
            ownership_spec_protobuf = common_pb2.OwnershipSpec()
            ownership_spec_protobuf.uid = ownership_spec.uid
            ownership_spec_protobuf.gid = ownership_spec.gid
            return ownership_spec_protobuf

        virtual_source_definition = VirtualSourceDefinition.from_dict(json.loads(request.virtual_source.parameters.json))
        virtual_source = VirtualSource(guid=request.virtual_source.guid,
                                       connection=request.virtual_source.connection,
                                       parameters=virtual_source_definition)

        repository = RepositoryDefinition.from_dict(json.loads(request.repository.parameters.json))

        if not self.mount_specification_impl:
            raise RuntimeError("An implementation for the virtual.mount_specification() operation has "
                               "not been defined.")

        virtual_mount_spec = self.mount_specification_impl(
            repository=repository,
            virtual_source=virtual_source)
        virtual_mount_spec_response = platform_pb2.VirtualMountSpecResponse()

        if virtual_mount_spec.ownership_specification:
            ownership_spec = to_protobuf_ownership_spec(virtual_mount_spec.ownership_specification)
            virtual_mount_spec_response.return_value.ownership_spec.CopyFrom(ownership_spec)

        mounts_list = [to_protobuf_single_mount(m) for m in virtual_mount_spec.mounts]
        virtual_mount_spec_response.return_value.mounts.extend(mounts_list)
        return virtual_mount_spec_response


class Plugin(object):

  def __init__(self):
    self.__discovery = DiscoveryOperations()
    self.__linked = LinkedOperations()
    self.__virtual = VirtualOperations()

  @property
  def discovery(self):
    return self.__discovery

  @property
  def linked(self):
      return self.__linked

  @property
  def virtual(self):
      return self.__virtual