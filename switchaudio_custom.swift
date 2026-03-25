import Foundation
import CoreAudio

// Helper to get string property
func getStringProperty(deviceID: AudioDeviceID, selector: AudioObjectPropertySelector) -> String? {
    var address = AudioObjectPropertyAddress(
        mSelector: selector,
        mScope: kAudioObjectPropertyScopeGlobal,
        mElement: kAudioObjectPropertyElementMain
    )
    
    var propertySize: UInt32 = 0
    if AudioObjectGetPropertyDataSize(deviceID, &address, 0, nil, &propertySize) != noErr {
        return nil
    }
    
    var name = "" as CFString
    if AudioObjectGetPropertyData(deviceID, &address, 0, nil, &propertySize, &name) != noErr {
        return nil
    }
    return name as String
}

// Check if device is output
func isOutputDevice(deviceID: AudioDeviceID) -> Bool {
    var address = AudioObjectPropertyAddress(
        mSelector: kAudioDevicePropertyStreams,
        mScope: kAudioDevicePropertyScopeOutput,
        mElement: kAudioObjectPropertyElementMain
    )
    var propertySize: UInt32 = 0
    if AudioObjectGetPropertyDataSize(deviceID, &address, 0, nil, &propertySize) != noErr {
        return false
    }
    return propertySize > 0
}

func getOutputDevices() -> [(id: AudioDeviceID, name: String)] {
    var address = AudioObjectPropertyAddress(
        mSelector: kAudioHardwarePropertyDevices,
        mScope: kAudioObjectPropertyScopeGlobal,
        mElement: kAudioObjectPropertyElementMain
    )
    
    var propertySize: UInt32 = 0
    if AudioObjectGetPropertyDataSize(UInt32(kAudioObjectSystemObject), &address, 0, nil, &propertySize) != noErr {
        return []
    }
    
    let deviceCount = Int(propertySize / UInt32(MemoryLayout<AudioDeviceID>.size))
    var deviceIDs = [AudioDeviceID](repeating: 0, count: deviceCount)
    if AudioObjectGetPropertyData(UInt32(kAudioObjectSystemObject), &address, 0, nil, &propertySize, &deviceIDs) != noErr {
        return []
    }
    
    var results: [(id: AudioDeviceID, name: String)] = []
    
    for id in deviceIDs {
        if isOutputDevice(deviceID: id) {
            if let name = getStringProperty(deviceID: id, selector: kAudioObjectPropertyName) {
                results.append((id: id, name: name))
            }
        }
    }
    return results
}

func setDefaultOutputDevice(deviceID: AudioDeviceID) -> Bool {
    var address = AudioObjectPropertyAddress(
        mSelector: kAudioHardwarePropertyDefaultOutputDevice,
        mScope: kAudioObjectPropertyScopeGlobal,
        mElement: kAudioObjectPropertyElementMain
    )
    
    var id = deviceID
    let size = UInt32(MemoryLayout<AudioDeviceID>.size)
    return AudioObjectSetPropertyData(UInt32(kAudioObjectSystemObject), &address, 0, nil, size, &id) == noErr
}

let args = CommandLine.arguments

if args.contains("-a") && args.contains("-t") && args.contains("output") {
    let devices = getOutputDevices()
    for device in devices {
        print(device.name)
    }
} else if let index = args.firstIndex(of: "-s"), index + 1 < args.count {
    let targetName = args[index + 1]
    let devices = getOutputDevices()
    
    if let match = devices.first(where: { $0.name == targetName }) {
        if setDefaultOutputDevice(deviceID: match.id) {
            print("Successfully set default output device to \(targetName)")
            exit(0)
        } else {
            print("Failed to set default output device")
            exit(1)
        }
    } else {
        print("Device not found")
        exit(1)
    }
} else {
    print("Usage:")
    print("  List output devices: -a -t output")
    print("  Set output device:   -s \"Device Name\"")
    exit(1)
}
