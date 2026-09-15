import QtQuick
import org.kde.kwin

import "../code/windows.js" as Windows


Item
{
    id: root


    DBusCall
    {
        id: updateWindowsCall

        service: "org.dofus.DofusFocusBridge"
        path: "/org/dofus/DofusFocusBridge"
        dbusInterface: "org.dofus.DofusFocusBridge"
        method: "update_windows"

        onFinished:
        {
            console.log(
                "[DOFUS FOCUS KWIN] Windows sent to Python bridge"
            );
        }

        onFailed:
        {
            console.log(
                "[DOFUS FOCUS KWIN] Failed to send windows to Python bridge"
            );
        }
    }


    function updateDofusWindows()
    {
        var windows =
            Windows.getDofusWindows();


        var windowIds = [];


        for(var i = 0; i < windows.length; i++)
        {
            var window =
                windows[i];


            windowIds.push(
                String(window.internalId)
            );
        }

        // Convert the array to a JSON string to avoid D-Bus type conversion issues.
        updateWindowsCall.arguments = [JSON.stringify(windowIds)];
        updateWindowsCall.call();
    }


    DBusCall
    {
        id: updateActiveWindowCall

        service: "org.dofus.DofusFocusBridge"
        path: "/org/dofus/DofusFocusBridge"
        dbusInterface: "org.dofus.DofusFocusBridge"
        method: "update_active_window"

        onFinished:
        {
        }

        onFailed:
        {
            console.log(
                "[DOFUS FOCUS KWIN] Failed to send active window to Python bridge"
            );
        }
    }


    Connections
    {
        target: Workspace


        function onWindowActivated(window)
        {
            var activeWindowId =
                Windows.getActiveDofusWindowId();

            updateActiveWindowCall.arguments =
                [activeWindowId];

            updateActiveWindowCall.call();
        }


        function onWindowAdded(window)
        {
            if(
                window.resourceClass === "Dofus.x64"
            )
            {
                updateDofusWindows();
            }
        }


        function onWindowRemoved(window)
        {
            if(
                window.resourceClass === "Dofus.x64"
            )
            {
                updateDofusWindows();
            }
        }
    }


    Component.onCompleted:
    {
        console.log(
            "[DOFUS FOCUS KWIN] KWin integration started"
        );


        var activeWindowId =
            Windows.getActiveDofusWindowId();


        updateActiveWindowCall.arguments =
            [activeWindowId];

        updateActiveWindowCall.call();
    }


    Component.onDestruction:
    {
        console.log(
            "[DOFUS FOCUS KWIN] KWin integration stopped"
        );
    }
}
