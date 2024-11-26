from fastapi import Query, WebSocket

from typing import Annotated
from typing_extensions import Doc

from netbox_proxbox.backend.session.netbox import NetboxSessionDep
from netbox_proxbox.backend.exception import ProxboxException

from netbox_proxbox.backend.logging import log

from netbox_proxbox.backend.cache import cache

from netbox_proxbox.backend.routes.netbox.generic.check_duplicate import _check_default
from netbox_proxbox.backend.routes.netbox.generic.get import (
    _get_by_id,
    _get_all,
    _get_by_kwargs,
)

from pydantic import BaseModel
import asyncio

class NetboxBase:
    """
    ## Class to handle Netbox Objects.
    
    !!! Logic
        - it will use `id` to get the `Objects` from Netbox if provided.\n
            - if object is returned, it will return it.\n
            - if object is not returned, it will raise an `ProxboxException`.
            
        - if 'site_id' is not provided, it will check if there's any Site registered on Netbox.\n
            - if there's no 'Objects' registered on Netbox, it will create a default one.\n
            - if there's any 'Objects' registered on Netbox, it will check if is Proxbox one by checking tag and name.\n
                
                -  if it's Proxbox one, it will return it.\n
                - if it's not Proxbox one, it will create a default one.\n
                
        - if 'all' is True, it will return all 'Objects' registered on Netbox.
    
    """

    def __init__(
        self,
        websocket: WebSocket,
        nb: NetboxSessionDep,
        id: Annotated[
            int,
            Query(
                title="Object ID"
            )
        ] = 0,
        all: Annotated[
            bool,
            Query(title="List All Objects", description="List all Objects registered on Netbox.")
        ] = False,
        default: Annotated[
            bool,
            Query(title="Create Default Object", description="Create a default Object if there's no Object registered on Netbox."),
        ] = False,
        ignore_tag: Annotated[
            bool,
            Query(
                title="Ignore Proxbox Tag",
                description="Ignore Proxbox tag filter when searching for objects in Netbox. This will return all Netbox objects, not only Proxbox related ones."
            ),
            Doc(
                "Ignore Proxbox tag filter when searching for objects in Netbox. This will return all Netbox objects, not only Proxbox related ones."
            ),
        ] = False,
        primary_field_value: str = "",
    ):
        
        self.nb = nb
        self.websocket = websocket
        self.id = id
        self.all = all
        self.default = default
        self.ignore_tag = ignore_tag
        self.primary_field_value = primary_field_value
        self.pynetbox_path = getattr(getattr(self.nb.session, self.app), self.endpoint)

        
    # New Implementantion of "default_dict" and "default_extra_fields".
    async def get_base_dict(self):
        "This method MUST be overwritten by the child class."
        return {}
    
    # Parameters to be used as Pynetbox class attributes. 
    # It should be overwritten by the child class.
    default_name: str = ""
    default_slug: str = ""
    default_description: str = ""
    
    app: str = ""
    endpoint: str = ""
    object_name: str = ""
    primary_field: str = ""
    

    async def get(
        self,
        **kwargs
    )
        self.base_dict = cache.get(self.endpoint)
        if self.base_dict is None:
            self.base_dict = await self.get_base_dict()
            cache.set(self.endpoint, self.base_dict)
    
        if self.id:
            return await _get_by_id(
                websocket=self.websocket,
                nb=self.nb,
                pynetbox_path=self.pynetbox_path,
                ignore_tag=self.ignore_tag,
                object_name=self.object_name,
                id=self.id
            )
        
        if kwargs:
            return await _get_by_kwargs(
                weboscket=self.websocket,
                pynetbox_path=self.pynetbox_path,
                endpoint=self.endpoint,
                primary_field=self.primary_field,
                primary_field_value=self.primary_field_value,
                object_name=self.object_name,
                **kwargs
            )
        
        if self.all:
            return await _get_all(
                websocket=self.websocket,
                nb=self.nb,
                pynetbox_path=self.pynetbox_path,
                ignore_tag=self.ignore_tag,
                object_name=self.object_name,
            )
        
        if self.pynetbox_path.count() == 0:
            
            await log(self.websocket, f"<span class='badge text-bg-blue' title='Get'><strong><i class='mdi mdi-download'></i></strong></span> There's no <strong>{self.object_name}</strong> registered on Netbox. Creating a DEFAULT ONE.")
            
            self.default: bool = True
            create_default_object = await self.post()
             
            if create_default_object is not None:
                await log(self.websocket, f"<span class='badge text-bg-blue' title='Get'><strong><i class='mdi mdi-download'></i></strong></span> Default <strong>{self.object_name}</strong> created successfully. {self.object_name} ID: {create_default_object.id}")
                return create_default_object
                
            else:
                await log(
                    self.websocket,
                    msg=f"<span class='badge text-bg-blue' title='Get'><strong><i class='mdi mdi-download'></i></strong></span> Error trying to create default <strong>{self.object_name}</strong> on Netbox.\n<strong>No objects found</strong>. Default <strong>{self.object_name}</strong> could not be created.",
                )
                
        
        # 2. Check if there's any 'Object' registered on Netbox.
        try:
            
            # 2.2
            # 2.2.1 If there's any 'Object' registered on Netbox, check if is Proxbox one by checking tag and name.
            try:
                await log(self.websocket, f"<span class='badge text-bg-blue' title='Get'><strong><i class='mdi mdi-download'></i></strong></span> <strong>{self.object_name}</strong> found on Netbox. Checking if it's 'Proxbox' one...")
                get_object = await asyncio.to_thread(self.pynetbox_path.get,
                    name=self.default_name,
                    slug=self.default_slug,
                    tag=[self.nb.tag.slug]
                )
                
            except ValueError as error:
                await log(
                    websocket=self.websocket,
                    msg=f"<span class='badge text-bg-blue' title='Get'><strong><i class='mdi mdi-download'></i></strong></span> Mutiple objects by get() returned. Proxbox will use filter(), delete duplicate objects and return only the first one.\n   > {error}"
                )
                
                get_object = await self._check_duplicate(
                    search_params = {
                        "name": self.default_name,
                        "slug": self.default_slug,
                        "tag": [self.nb.tag.slug],
                    }
                )

            if get_object is not None:
                await log(self.websocket, f"<span class='badge text-bg-blue' title='Get'><strong><i class='mdi mdi-download'></i></strong></span> The <strong>{self.object_name}</strong> found is from 'Proxbox' (because it has the tag). Returning it.")
                return get_object
            
            # 2.2.2. If it's not Proxbox one, create a default one.
            await log(
                self.websocket,
                f"<span class='badge text-bg-blue' title='Get'><strong><i class='mdi mdi-download'></i></strong></span> The <strong>{self.object_name}</strong> object found IS NOT from 'Proxbox'. Creating a default one."
            )
            
            self.default: bool = True
            
            default_object = await self.post()
            
            if default_object:
                return default_object
        
        except ProxboxException as error:
            await log(websocket=self.websocket, msg=f'{error}')
            
        except Exception as error:
            await log(
                websocket=self.websocket,
                msg=f"Error trying to get <strong>{self.object_name}</strong> from Netbox.\nPython Error: {error}",
            )
    
    
    async def post(
        self,
        data: dict | None =  None,
    ): 
        """
        ### Asynchronously handles the POST request to create an object on Netbox.
        
        **Args:**
        - **data (dict, optional):** The data payload for creating the object. Defaults to None.
        
        **Returns:**
        - **response:** The created object response from Netbox if successful, or the existing object if a duplicate is found.
        - **None:** If the object could not be created due to a unique constraint violation.
       
        **Raises:**
        - **ProxboxException:** If there is an error parsing the Pydantic model to a dictionary, 
                              if required fields are missing, or if there is an error during the creation process.
        
        **Workflow:**
            1. Retrieves the base dictionary from the cache or fetches it if not present.
            2. Logs the creation attempt.
            3. Converts the Pydantic model to a dictionary if necessary.
            4. Generates a slug from the name or model field if not provided.
            5. Uses the base dictionary if no data is provided or if default is set.
            6. Merges the base dictionary with the provided data.
            7. Checks for duplicates.
            8. Appends the Proxbox tag to the tags field if present, or creates it.
            9. Attempts to create the object on Netbox.
            10. Logs the success or failure of the creation attempt.
        """ 
        
        # 1. Retrieves the base dictionary from the cache or fetches it if not present.
        self.base_dict: dict = cache.get(self.endpoint)
        if self.base_dict is None:
            self.base_dict = await self.get_base_dict()
            
            # 1.1. Cache the base_dict.
            cache.set(self.endpoint, self.base_dict)

        if data:
            await log(self.websocket, f"<span class='badge text-bg-red' title='Post'><strong><i class='mdi mdi-upload'></i></strong></span> Creating <strong>{self.object_name}</strong> object on Netbox.")
        
            #if isinstance(data, dict) is False:
            #    try:
            #        # Convert Pydantic model to Dict through 'model_dump' Pydantic method.
            #        data = data.model_dump(exclude_unset=True)
            #        
            #    except Exception as error:
            #        raise ProxboxException(
            #            message="<span class='text-red'><strong><i class='mdi mdi-upload'></i></strong></span> <span class='text-red'><strong><i class='mdi mdi-error'></i></strong></span> <strong>[POST]</strong> Error parsing Pydantic model to Dict.",
            #            python_exception=f"{error}",
            #        )
                
            # If no explicit slug was provided by the payload, create one based on the name.
            if data.get("slug"):
                if not self.primary_field:
                    await log(self.websocket, "<span class='badge text-bg-red' title='Post'><strong><i class='mdi mdi-upload'></i></strong></span> <strong>SLUG</strong> field not provided on the payload. Creating one based on the NAME or MODEL field.")
                    try:
                        data["slug"] = data.get("name", "").replace(" ", "-").lower()
                    except AttributeError:
                        
                        try:
                            data["slug"] = data.get("model", "").replace(" ", "-").lower()
                        except AttributeError:
                            await log(
                                websocket=self.websocket,
                                msg="<span class='badge text-bg-red' title='Post'><strong><i class='mdi mdi-upload'></i></strong></span> No <strong>NAME</strong> or <strong>model</strong> field provided on the payload. Please provide one of them.",
                            )
                
        if self.default or data is None:
            await log(self.websocket, f"<span class='badge text-bg-red' title='Post'><strong><i class='mdi mdi-upload'></i></strong></span> Creating DEFAULT <strong>{self.object_name}</strong> object on Netbox.")
            data = self.base_dict
            
        try:

            """
            Merge base_dict and data dict.
            The fields not specificied on data dict will be filled with the base_dict values.
            """
            data_merged: dict = self.base_dict | data
            
            check_duplicate_result = await self._check_duplicate(object = data_merged)
            
            if check_duplicate_result is None:
                response = None
                
                # Check if tags field exists on the payload and if true, append the Proxbox tag. If not, create it.
                if data_merged.get("tags") is None:
                    data_merged["tags"] = [self.nb.tag.id]
                else:
                    data_merged["tags"].append(self.nb.tag.id)
                 
                try:
                    await log(self.websocket, f"<span class='badge text-bg-red' title='Post'><strong><i class='mdi mdi-upload'></i></strong></span> Trying to create <strong>{self.object_name}</strong> object on Netbox.")
                    
                    response = await asyncio.to_thread(self.pynetbox_path.create, data_merged)
                    
                    if response:
                        await log(
                            self.websocket,
                            f"<span class='badge text-bg-red' title='Post'><strong><i class='mdi mdi-upload'></i></strong></span> <strong>{self.object_name}</strong> object created successfully. {self.object_name} ID: {getattr(response, 'id', 'Not specified.')}"
                        )
                        return response
                    
                    else:
                        await log(
                            self.websocket,
                            f"<span class='badge text-bg-red' title='Post'><strong><i class='mdi mdi-upload'></i></strong></span> <strong>{self.object_name}</strong> object could not be created.\nPayload: <code>{data}</code>"
                        )
                        
                except Exception as error:
                    
                    if "['The fields virtual_machine, name must make a unique set.']}" in f"{error}":
                        await log(
                            self.websocket,
                            f"Error trying to create <strong>Virtual Machine Interface</strong> because the same <strong>virtual_machine</strong> name already exists.\nPayload: {data}"
                        )
                        return None
                    
                    if "['Virtual machine name must be unique per cluster.']" in f"{error}":
                        await log(
                            self.websocket,
                            f"Error trying to create <strong>Virtual Machine</strong> because Virtual Machine Name <strong>must be unique.</strong>\nPayload: {data}"
                        )
                        return None
                    
                    else:
                        await log(
                            self.websocket,
                            msg=f"<span class='badge text-bg-red' title='Post'><strong><i class='mdi mdi-upload'></i></strong></span> Error trying to create <strong>{self.object_name}</strong> object on Netbox.\n   > {f'{error}'}",
                        )
            else:
                await log(self.websocket, f"<span class='badge text-bg-red' title='Post'><strong><i class='mdi mdi-upload'></i></strong></span> <strong>{self.object_name}</strong> object already exists on Netbox. Returning it.")
                return check_duplicate_result

        except Exception as error:
            raise ProxboxException(
                message=f"Error trying to create <strong>{self.object_name}</strong> on Netbox.",
                detail=f"Payload provided: {data}",
                python_exception=f"{error}"
            )
        
    async def _check_duplicate(
        self,
        search_params: dict = {},
        object: dict = {},
    ):
        """
        Asynchronously checks for duplicate objects in Netbox before creating a new one.
        This method performs several checks to determine if an object already exists in Netbox based on various criteria 
        such as default settings, primary fields, and specific attributes provided in the `object` parameter.
        
        **Args:**
        - **search_params (dict, optional):** Parameters to search for duplicates. Defaults to None.
        - **object (dict, optional):** The object to check for duplication. Defaults to None.
        
        **Returns:**
        - **dict or None:** The existing object if a duplicate is found, otherwise None.
        
        **Raises:**
        - **ProxboxException:** If an error occurs during the duplicate check process.
        """

        await log(
            websocket=self.websocket,
            msg=f"<span class='badge text-bg-purple' title='Check Duplicate'>
                <i class='mdi mdi-content-duplicate'></i>
            </span> Checking if <strong>{self.object_name}</strong> exists on Netbox before creating it."
        )

        # Check if Proxbox default object exists in Netbox.
        if self.default:
            check_default = await _check_default(
                websocket=self.websocket,
                pynetbox_path=self.pynetbox_path,
                default_name=self.default_name,
                default_slug=self.default_slug,
                object_name=self.object_name,
                nb=self.nb,
            )
            if check_default is not None:
                return check_default
            
            
            
        
        