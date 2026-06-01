package com.srp.client.renderer;

import com.srp.client.model.OrbScaryModel;
import com.srp.entity.OrbScaryEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class OrbScaryRenderer extends GeoEntityRenderer<OrbScaryEntity> {

    public OrbScaryRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new OrbScaryModel());
    }
}
