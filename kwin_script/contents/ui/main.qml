import QtQuick
import org.kde.kwin

import "../code/windows.js" as Windows


Item
{
    id: root


    DBusCall
    {
        id: updateWindowsCall

        service: "org.ilan.DofusFocusBridge"
        path: "/org/ilan/DofusFocusBridge"
        dbusInterface: "org.ilan.DofusFocusBridge"
        method: "update_windows"

        onFinished:
        {
            console.log(
                "[DOFUS FOCUS TRAY] Windows sent to Python bridge"
            );
        }

        onFailed:
        {
            console.log(
                "[DOFUS FOCUS TRAY] Failed to send windows to Python bridge"
            );
        }
    }


    function dumpDofusWindows()
    {
        var windows =
            Windows.getDofusWindows();


        console.log(
            "[DOFUS FOCUS TRAY] Dofus windows:",
            windows.length
        );


        var windowIds = [];


        for(var i = 0; i < windows.length; i++)
        {
            var window =
                windows[i];


            console.log(
                "[DOFUS FOCUS TRAY]",
                "index =", i,
                "| caption =", window.caption,
                "| resourceClass =", window.resourceClass,
                "| internalId =", window.internalId
            );


            windowIds.push(
                String(window.internalId)
            );
        }

        // On transforme le tableau en chaîne JSON pour éviter les conflits de types D-Bus
        updateWindowsCall.arguments = [JSON.stringify(windowIds)];
        updateWindowsCall.call();
    }


    DBusCall
    {
        id: updateActiveWindowCall

        service: "org.ilan.DofusFocusBridge"
        path: "/org/ilan/DofusFocusBridge"
        dbusInterface: "org.ilan.DofusFocusBridge"
        method: "update_active_window"

        onFinished:
        {
            console.log(
                "[DOFUS FOCUS TRAY] Active window sent to Python bridge"
            );
        }

        onFailed:
        {
            console.log(
                "[DOFUS FOCUS TRAY] Failed to send active window to Python bridge"
            );
        }
    }


    Connections
    {
        target: Workspace


        function onWindowActivated(window)
        {
            var activeWindow =
                Windows.getActiveWindow();


            console.log(
                "[DOFUS FOCUS TRAY] Active Dofus window:",
                activeWindow
            );

            console.log(
                "[DOFUS FOCUS TRAY] Sending active window to Python bridge:",
                activeWindow
            );

            updateActiveWindowCall.arguments =
                [activeWindow];

            updateActiveWindowCall.call();

            console.log(
                "[DOFUS FOCUS TRAY] update_active_window call issued"
            );
        }


        function onWindowAdded(window)
        {
            if(
                window.resourceClass === "Dofus.x64"
            )
            {
                dumpDofusWindows();
            }
        }


        function onWindowRemoved(window)
        {
            if(
                window.resourceClass === "Dofus.x64"
            )
            {
                dumpDofusWindows();
            }
        }
    }


    Component.onCompleted:
    {
        console.log(
            "[DOFUS FOCUS TRAY] KWin bridge started"
        );


        var activeWindow =
            Windows.getActiveWindow();


        updateActiveWindowCall.arguments =
            [activeWindow];

        updateActiveWindowCall.call();
    }


    Component.onDestruction:
    {
        console.log(
            "[DOFUS FOCUS TRAY] KWin bridge stopped"
        );
    }
}
