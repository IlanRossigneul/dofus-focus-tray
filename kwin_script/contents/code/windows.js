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


function getActiveWindow()
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

        console.log(
            "[DOFUS FOCUS TRAY] Setting Workspace.activeWindow to target"
        );

        try
        {
            // C'est l'API exacte sous KWin 6
            Workspace.activeWindow = window;

            console.log(
                "[DOFUS FOCUS TRAY] Workspace.activeWindow successfully assigned"
            );

            return true;
        }
        catch(error)
        {
            console.log(
                "[DOFUS FOCUS TRAY] Failed to set activeWindow:",
                error
            );

            return false;
        }
    }

    return false;
}
