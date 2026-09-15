function getDofusWindows()
{
    var windows = [];

    for(var i = 0; i < Workspace.windows.length; i++)
    {
        var window = Workspace.windows[i];

        if(window.resourceClass !== "Dofus.x64")
            continue;

        windows.push(
            {
                internalId: String(window.internalId),
                caption: window.caption,
                resourceClass: window.resourceClass
            }
        );
    }

    return windows;
}


function getActiveDofusWindowId()
{
    var window =
        Workspace.activeWindow;


    if(
        !window
    )
    {
        return "";
    }


    if(
        window.resourceClass !== "Dofus.x64"
    )
    {
        return "";
    }


    return String(
        window.internalId
    );
}


function activateWindow(internalId)
{
    for(var i = 0; i < Workspace.windows.length; i++)
    {
        var window = Workspace.windows[i];

        if(window.resourceClass !== "Dofus.x64")
        {
            continue;
        }

        if(String(window.internalId) !== String(internalId))
        {
            continue;
        }

        try
        {
            // This is the exact API exposed by KWin 6.
            Workspace.activeWindow = window;

            return true;
        }
        catch(error)
        {
            return false;
        }
    }

    return false;
}
